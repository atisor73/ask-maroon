import re
import sqlite3
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
ARCHIVE_DB = OUTPUT_DIR / "metadata" / "archive.db"
CHUNKS_DB = OUTPUT_DIR / "metadata" / "chunks.db"
FAILED_DOCS_LOG = OUTPUT_DIR / "metadata" / "chunk_page_mapping_failures.txt"
PAGE_TEXT_CACHE_DIR = OUTPUT_DIR / "metadata" / "page_text_cache"
MIN_TOKEN_LENGTH = 3
PAGE_LOOKAHEAD = 4
COMMIT_EVERY_DOCS = 25


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def tokenize(text: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalize_text(text))
        if len(token) >= MIN_TOKEN_LENGTH
    ]


def build_token_counter(text: str) -> Counter:
    return Counter(tokenize(text))


def overlap_score(chunk_counter: Counter, page_counter: Counter) -> float:
    """
    Simple lexical overlap score between a chunk and a page/window of pages.

    We use token-frequency overlap normalized by chunk token mass.
    This is a practical first pass for noisy OCR alignment.
    """
    if not chunk_counter:
        return 0.0

    overlap = 0
    for token, count in chunk_counter.items():
        overlap += min(count, page_counter.get(token, 0))

    total = sum(chunk_counter.values())
    return overlap / total if total else 0.0


def extract_page_texts(pdf_path: Path) -> List[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Need pypdf or PyPDF2 installed to map chunks to PDF pages."
            ) from exc

    reader = PdfReader(str(pdf_path))
    page_texts = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        page_texts.append(text)
    return page_texts


def cache_path_for_doc(doc_id: str) -> Path:
    return PAGE_TEXT_CACHE_DIR / "{}.json".format(doc_id)


def load_or_extract_page_texts(doc_id: str, pdf_path: Path) -> List[str]:
    PAGE_TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = cache_path_for_doc(doc_id)

    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    page_texts = extract_page_texts(pdf_path)
    cache_path.write_text(json.dumps(page_texts), encoding="utf-8")
    return page_texts


def ensure_chunk_page_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(chunks)").fetchall()
    }

    if "page_number" not in existing:
        conn.execute("ALTER TABLE chunks ADD COLUMN page_number INTEGER")
    if "page_match_score" not in existing:
        conn.execute("ALTER TABLE chunks ADD COLUMN page_match_score REAL")

    conn.commit()


def fetch_documents_with_chunks(
    archive_conn: sqlite3.Connection,
    chunks_conn: sqlite3.Connection,
) -> List[sqlite3.Row]:
    archive_conn.row_factory = sqlite3.Row
    chunks_conn.row_factory = sqlite3.Row

    chunk_doc_ids = [
        row["doc_id"]
        for row in chunks_conn.execute(
            """
            SELECT DISTINCT doc_id
            FROM chunks
            ORDER BY doc_id
            """
        ).fetchall()
    ]

    if not chunk_doc_ids:
        return []

    placeholders = ",".join("?" for _ in chunk_doc_ids)
    return archive_conn.execute(
        f"""
        SELECT doc_id, pdf_path
        FROM documents
        WHERE doc_id IN ({placeholders})
        ORDER BY doc_id
        """,
        chunk_doc_ids,
    ).fetchall()


def fetch_chunks_for_document(
    chunks_conn: sqlite3.Connection,
    doc_id: str,
    only_unmapped: bool = True,
) -> List[sqlite3.Row]:
    where_clause = "doc_id = ?"
    if only_unmapped:
        where_clause += " AND page_number IS NULL"

    return chunks_conn.execute(
        """
        SELECT chunk_id, chunk_index, text
        FROM chunks
        WHERE {}
        ORDER BY chunk_index
        """.format(where_clause),
        (doc_id,),
    ).fetchall()


def document_is_already_mapped(chunks_conn: sqlite3.Connection, doc_id: str) -> bool:
    row = chunks_conn.execute(
        """
        SELECT
            COUNT(*) AS total_chunks,
            SUM(CASE WHEN page_number IS NOT NULL THEN 1 ELSE 0 END) AS mapped_chunks
        FROM chunks
        WHERE doc_id = ?
        """,
        (doc_id,),
    ).fetchone()

    if row is None:
        return False
    total_chunks = row[0] or 0
    mapped_chunks = row[1] or 0
    return total_chunks > 0 and total_chunks == mapped_chunks


def best_page(
    chunk_text: str,
    page_counters: List[Counter],
    start_page: int = 1,
) -> Tuple[Optional[int], float]:
    chunk_counter = build_token_counter(chunk_text)
    if not chunk_counter or not page_counters:
        return None, 0.0

    best_page_number = None
    best_score = 0.0

    start_index = max(1, start_page)
    end_index = min(len(page_counters), start_index + PAGE_LOOKAHEAD)

    # Use chunk order to bias the search forward through the document.
    # If the local search window fails badly, fall back to all pages.
    candidate_indices = list(range(start_index, end_index + 1))
    if not candidate_indices:
        candidate_indices = list(range(1, len(page_counters) + 1))

    for index in candidate_indices:
        page_counter = page_counters[index - 1]
        score = overlap_score(chunk_counter, page_counter)
        if score > best_score:
            best_score = score
            best_page_number = index

    if best_page_number is None or best_score < 0.15:
        for index, page_counter in enumerate(page_counters, start=1):
            score = overlap_score(chunk_counter, page_counter)
            if score > best_score:
                best_score = score
                best_page_number = index

    return best_page_number, best_score


def update_chunk_page_mapping(
    chunks_conn: sqlite3.Connection,
    chunk_id: str,
    page_number: Optional[int],
    page_match_score: float,
) -> None:
    chunks_conn.execute(
        """
        UPDATE chunks
        SET page_number = ?, page_match_score = ?
        WHERE chunk_id = ?
        """,
        (page_number, page_match_score, chunk_id),
    )


def append_failure(doc_id: str, pdf_path: Path, reason: str) -> None:
    FAILED_DOCS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FAILED_DOCS_LOG.open("a", encoding="utf-8") as handle:
        handle.write("{}\t{}\t{}\n".format(doc_id, pdf_path, reason))


def main() -> None:
    if not ARCHIVE_DB.exists():
        raise FileNotFoundError("Missing archive metadata database: {}".format(ARCHIVE_DB))
    if not CHUNKS_DB.exists():
        raise FileNotFoundError("Missing chunks database: {}".format(CHUNKS_DB))

    archive_conn = sqlite3.connect(ARCHIVE_DB)
    chunks_conn = sqlite3.connect(CHUNKS_DB)

    processed_docs = 0
    processed_chunks = 0
    skipped_docs = 0
    failed_docs = 0
    docs_since_commit = 0

    try:
        ensure_chunk_page_columns(chunks_conn)
        documents = fetch_documents_with_chunks(archive_conn, chunks_conn)

        for doc_row in tqdm(documents, total=len(documents), desc="Mapping chunks to pages", unit="doc"):
            pdf_path = Path(doc_row["pdf_path"])
            if not pdf_path.exists():
                append_failure(doc_row["doc_id"], pdf_path, "pdf_missing")
                failed_docs += 1
                continue
            if pdf_path.stat().st_size == 0:
                append_failure(doc_row["doc_id"], pdf_path, "pdf_empty")
                failed_docs += 1
                continue

            if document_is_already_mapped(chunks_conn, doc_row["doc_id"]):
                skipped_docs += 1
                continue

            try:
                page_texts = load_or_extract_page_texts(doc_row["doc_id"], pdf_path)
            except Exception as exc:
                append_failure(doc_row["doc_id"], pdf_path, exc.__class__.__name__)
                failed_docs += 1
                continue
            if not page_texts:
                append_failure(doc_row["doc_id"], pdf_path, "no_page_text")
                failed_docs += 1
                continue

            page_counters = [build_token_counter(text) for text in page_texts]

            chunk_rows = fetch_chunks_for_document(chunks_conn, doc_row["doc_id"], only_unmapped=True)
            if not chunk_rows:
                skipped_docs += 1
                continue

            last_page_number = 1
            for chunk_row in chunk_rows:
                page_number, score = best_page(
                    chunk_row["text"],
                    page_counters,
                    start_page=last_page_number,
                )
                update_chunk_page_mapping(
                    chunks_conn,
                    chunk_id=chunk_row["chunk_id"],
                    page_number=page_number,
                    page_match_score=score,
                )
                if page_number is not None:
                    last_page_number = page_number
                processed_chunks += 1

            processed_docs += 1
            docs_since_commit += 1

            if docs_since_commit >= COMMIT_EVERY_DOCS:
                chunks_conn.commit()
                docs_since_commit = 0

        chunks_conn.commit()
    finally:
        archive_conn.close()
        chunks_conn.close()

    print("Mapped {} chunks across {} documents".format(processed_chunks, processed_docs))
    print("Skipped {} documents already mapped or with no unmapped chunks".format(skipped_docs))
    print("Failed {} documents".format(failed_docs))
    print("Failure log: {}".format(FAILED_DOCS_LOG))


if __name__ == "__main__":
    main()
