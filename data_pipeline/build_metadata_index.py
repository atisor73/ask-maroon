"""
Build a document-level metadata index for the Maroon archive outputs.

This script scans the local plain-text corpus, matches each text file to the
expected PDF location and any scraped metadata from documents.json, and writes
a normalized document table to SQLite. It also optionally exports the same rows
to parquet for easier downstream analysis.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
PDF_DIR = OUTPUT_DIR / "pdfs"
TEXT_DIR = OUTPUT_DIR / "plain_text"
DOCUMENTS_JSON = OUTPUT_DIR / "documents.json"
METADATA_DIR = OUTPUT_DIR / "metadata"
DB_PATH = METADATA_DIR / "archive.db"
PARQUET_PATH = METADATA_DIR / "docs.parquet"


# Load the scraped documents JSON file and index its records by document ID.
def load_documents_json(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}

    records = json.loads(path.read_text(encoding="utf-8"))
    by_id = {}
    for record in records:
        doc_id = record.get("id")
        if doc_id:
            by_id[doc_id] = record
    return by_id

# Recursively find all plain-text files under the given root while skipping notebook checkpoint artifacts.
def iter_text_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.txt")
        if ".ipynb_checkpoints" not in path.parts and not path.name.endswith("-checkpoint.txt")
    )

# Derive a document ID from a text filename by using its stem.
def extract_doc_id(text_path: Path) -> str:
    return text_path.stem

# Infer the matching PDF file path for a given text path using the output directory layout.
def infer_pdf_path(text_path: Path) -> Path:
    relative = text_path.relative_to(TEXT_DIR)
    return PDF_DIR / relative.with_suffix(".pdf")

# Try to reconstruct an ISO-style date string from the document ID naming convention.
def infer_date_from_doc_id(doc_id: str) -> Optional[str]:
    parts = doc_id.split("-")
    if len(parts) < 4:
        return None

    year = parts[-2]
    month_day = parts[-1]
    if len(year) == 4 and len(month_day) == 4:
        return f"{year}-{month_day[:2]}-{month_day[2:]}"
    return None


# Count the number of pages in a PDF, falling back between supported reader libraries if needed.
def count_pdf_pages(pdf_path: Path) -> Optional[int]:
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        pass

    try:
        from PyPDF2 import PdfReader  # type: ignore

        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return None

# Classify whether OCR/plain text exists for a document based on the text length.
def detect_ocr_status(text_length: int) -> str:
    if text_length == 0:
        return "empty_text"
    return "text_present"

# Build one normalized metadata row for a document by combining file-derived info with scraped metadata.
def build_document_row(text_path: Path, docs_by_id: Dict[str, dict]) -> dict:
    doc_id = extract_doc_id(text_path)
    source = docs_by_id.get(doc_id, {})
    pdf_path = infer_pdf_path(text_path)

    date = source.get("date") or infer_date_from_doc_id(doc_id)
    year = source.get("year") or (date[:4] if date else None)
    text_length = len(text_path.read_text(encoding="utf-8", errors="ignore"))

    return {
        "doc_id": doc_id,
        "year": year,
        "date": date,
        "title": source.get("title"),
        "pdf_path": str(pdf_path),
        "text_path": str(text_path),
        "source_url": source.get("doc_url"),
        "pdf_url": source.get("pdf_url"),
        "plain_text_url": source.get("plain_text_url"),
        "page_count": count_pdf_pages(pdf_path) if pdf_path.exists() else None,
        "ocr_status": detect_ocr_status(text_length),
        "text_length": text_length,
    }


# Create the documents table if needed and clear any previously indexed rows before rebuilding the index.
def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            year TEXT,
            date TEXT,
            title TEXT,
            pdf_path TEXT NOT NULL,
            text_path TEXT,
            source_url TEXT,
            pdf_url TEXT,
            plain_text_url TEXT,
            page_count INTEGER,
            ocr_status TEXT,
            text_length INTEGER
        )
        """
    )
    conn.execute("DELETE FROM documents")

# Insert the prepared document metadata rows into the SQLite documents table and commit the transaction.
def insert_rows(conn: sqlite3.Connection, rows: Iterable[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO documents (
            doc_id, year, date, title, pdf_path, text_path, source_url,
            pdf_url, plain_text_url, page_count, ocr_status, text_length
        ) VALUES (
            :doc_id, :year, :date, :title, :pdf_path, :text_path, :source_url,
            :pdf_url, :plain_text_url, :page_count, :ocr_status, :text_length
        )
        """,
        rows,
    )
    conn.commit()


# Export the indexed document rows to parquet when pandas and parquet support are available.
def export_parquet(rows: list[dict], path: Path) -> None:
    try:
        import pandas as pd  # type: ignore
    except Exception:
        print("Skipping parquet export: pandas is not installed.")
        return

    try:
        df = pd.DataFrame(rows)
        df.to_parquet(path, index=False)
    except Exception as exc:
        print(f"Skipping parquet export: {exc}")


# Orchestrate metadata indexing by reading source files, rebuilding the SQLite table, and writing parquet output.
def main() -> None:
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    docs_by_id = load_documents_json(DOCUMENTS_JSON)
    text_files = list(iter_text_files(TEXT_DIR))
    rows = [build_document_row(text_path, docs_by_id) for text_path in text_files]

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        insert_rows(conn, rows)
    finally:
        conn.close()

    export_parquet(rows, PARQUET_PATH)

    print(f"Indexed {len(rows)} documents into {DB_PATH}")
    print(f"Parquet target: {PARQUET_PATH}")


if __name__ == "__main__":
    main()
