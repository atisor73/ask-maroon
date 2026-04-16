"""
Create the chunk-level text corpus used by archive search.

Given cleaned plain-text files and document metadata, this script normalizes
text, splits it into overlapping chunks, and writes those chunks to chunks.db.
It also builds an FTS5 table so the same chunk corpus can support keyword
search in addition to embedding-based retrieval.

Methodology:
Chunks are created by approximate word count, using whitespace-based counting 
and simple sentence/paragraph heuristics, not by character-count or model tokens.

The pipeline is basically
- Get documents with text paths from archive.db
- Map each original text file to its cleaned version
- Read cleaned text
- Normalize spacing a bit more
- Split into paragraph/sentence-sized units
- Assemble those units into overlapping chunks
- Each chunk is about 500 words with 75 words overlapping in between chunks
- Write the chunks into chunks.db and chunks_fts
"""

import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
METADATA_DB = OUTPUT_DIR / "metadata" / "archive.db"
CHUNKS_DB = OUTPUT_DIR / "metadata" / "chunks.db"
CLEANED_DIR = OUTPUT_DIR / "plain_text_cleaned"

CHUNK_WORDS = 500
OVERLAP_WORDS = 75

WORD_RE = re.compile(r"\S+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Normalize raw text spacing and line breaks so chunking operates on a cleaner, more consistent input.
def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

# Split a document into paragraph- or sentence-sized units that can be assembled into chunks.
def split_units(text: str) -> List[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    units: List[str] = []

    for paragraph in paragraphs:
        words = paragraph.split()
        if len(words) <= CHUNK_WORDS:
            units.append(paragraph)
            continue

        sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(paragraph) if part.strip()]
        if len(sentences) <= 1:
            units.extend(slice_words(words, CHUNK_WORDS))
        else:
            units.extend(sentences)

    return units

# Break an oversized word list into fixed-size slices when paragraph or sentence boundaries are unavailable.
def slice_words(words: List[str], size: int) -> List[str]:
    slices = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        slices.append(" ".join(words[start:end]))
        start = end
    return slices

# Count the number of whitespace-delimited word tokens in a text span.
def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))

# Assemble overlapping retrieval chunks from normalized text while roughly respecting the target chunk size.
def chunk_document(text: str) -> List[Dict[str, object]]:
    units = split_units(normalize_text(text))
    chunks: List[Dict[str, object]] = []
    current_units: List[str] = []
    current_words = 0

    for unit in units:
        unit_words = count_words(unit)

        if current_units and current_words + unit_words > CHUNK_WORDS:
            chunk_text = " ".join(current_units).strip()
            chunks.append({"text": chunk_text, "word_count": count_words(chunk_text)})

            overlap_units: List[str] = []
            overlap_words = 0
            for existing in reversed(current_units):
                existing_words = count_words(existing)
                if overlap_words + existing_words > OVERLAP_WORDS and overlap_units:
                    break
                overlap_units.insert(0, existing)
                overlap_words += existing_words

            current_units = overlap_units[:]
            current_words = sum(count_words(item) for item in current_units)

        current_units.append(unit)
        current_words += unit_words

    if current_units:
        chunk_text = " ".join(current_units).strip()
        chunks.append({"text": chunk_text, "word_count": count_words(chunk_text)})

    return chunks

# Map an original plain-text path to its cleaned-text counterpart in the cleaned output directory.
def cleaned_text_path(original_text_path: Optional[str]) -> Optional[Path]:
    if not original_text_path:
        return None

    original = Path(original_text_path)
    try:
        relative = original.relative_to(OUTPUT_DIR / "plain_text")
    except ValueError:
        return None
    return CLEANED_DIR / relative


# Rebuild the chunks database schema, including both the chunk table and its FTS index.
def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("DROP TABLE IF EXISTS chunks_fts")
    conn.execute("DROP TABLE IF EXISTS chunks")

    conn.execute(
        """
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            year TEXT,
            date TEXT,
            source_text_path TEXT,
            text TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
        )
        """
    )

    conn.execute(
        """
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            doc_id UNINDEXED,
            year UNINDEXED,
            date UNINDEXED,
            text
        )
        """
    )

    conn.execute("CREATE INDEX idx_chunks_doc_id ON chunks(doc_id)")
    conn.execute("CREATE INDEX idx_chunks_date ON chunks(date)")


# Load all documents with available text paths from the metadata database in chronological order.
def iter_documents(metadata_conn: sqlite3.Connection) -> List[sqlite3.Row]:
    metadata_conn.row_factory = sqlite3.Row
    rows = metadata_conn.execute(
        """
        SELECT doc_id, year, date, text_path
        FROM documents
        WHERE text_path IS NOT NULL
        ORDER BY date, doc_id
        """
    ).fetchall()
    return rows

# Insert one document’s chunks into both the main chunks table and the FTS table, then return how many were written.
def insert_document_chunks(
    conn: sqlite3.Connection,
    doc_id: str,
    year: Optional[str],
    date: Optional[str],
    source_text_path: str,
    chunks: List[Dict[str, object]],
) -> int:
    chunk_rows = []
    fts_rows = []

    for index, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}::chunk-{index:04d}"
        chunk_rows.append(
            {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "chunk_index": index,
                "year": year,
                "date": date,
                "source_text_path": source_text_path,
                "text": chunk["text"],
                "word_count": chunk["word_count"],
            }
        )
        fts_rows.append(
            {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "year": year,
                "date": date,
                "text": chunk["text"],
            }
        )

    conn.executemany(
        """
        INSERT INTO chunks (
            chunk_id, doc_id, chunk_index, year, date, source_text_path, text, word_count
        ) VALUES (
            :chunk_id, :doc_id, :chunk_index, :year, :date, :source_text_path, :text, :word_count
        )
        """,
        chunk_rows,
    )
    conn.executemany(
        """
        INSERT INTO chunks_fts (chunk_id, doc_id, year, date, text)
        VALUES (:chunk_id, :doc_id, :year, :date, :text)
        """,
        fts_rows,
    )
    return len(chunk_rows)


# Orchestrate cleaned-text chunking by reading documents, generating overlapping chunks, and writing them to chunks.db.
def main() -> None:
    if not METADATA_DB.exists():
        raise FileNotFoundError(f"Missing metadata database: {METADATA_DB}")

    if not CLEANED_DIR.exists():
        raise FileNotFoundError(f"Missing cleaned text directory: {CLEANED_DIR}")

    CHUNKS_DB.parent.mkdir(parents=True, exist_ok=True)

    metadata_conn = sqlite3.connect(METADATA_DB)
    chunks_conn = sqlite3.connect(CHUNKS_DB)

    skipped = 0
    total_chunks = 0

    try:
        init_db(chunks_conn)
        documents = iter_documents(metadata_conn)

        for row in tqdm(documents, total=len(documents), desc="Chunking cleaned text", unit="doc"):
            cleaned_path = cleaned_text_path(row["text_path"])
            if cleaned_path is None or not cleaned_path.exists():
                skipped += 1
                continue

            text = cleaned_path.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                skipped += 1
                continue

            chunks = chunk_document(text)
            total_chunks += insert_document_chunks(
                chunks_conn,
                doc_id=row["doc_id"],
                year=row["year"],
                date=row["date"],
                source_text_path=str(cleaned_path),
                chunks=chunks,
            )

        chunks_conn.commit()
    finally:
        metadata_conn.close()
        chunks_conn.close()

    print(f"Wrote {total_chunks} chunks to {CHUNKS_DB}")
    print(f"Skipped {skipped} documents with missing or empty cleaned text.")


if __name__ == "__main__":
    main()
