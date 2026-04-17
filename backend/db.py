import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

ARCHIVE_DB = OUTPUT_DIR / "metadata" / "archive.db"
CHUNKS_DB = OUTPUT_DIR / "metadata" / "chunks.db"

BASE_DOCUMENT_FIELDS = [
    "doc_id",
    "year",
    "date",
    "title",
    "pdf_path",
    "text_path",
    "source_url",
    "pdf_url",
    "plain_text_url",
]
OPTIONAL_DOCUMENT_FIELDS = [
    "pdf_r2_key",
    "text_r2_key",
]


def get_archive_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(ARCHIVE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_chunks_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(CHUNKS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_document_select_fields(conn: sqlite3.Connection) -> str:
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(documents)").fetchall()
    }
    fields = list(BASE_DOCUMENT_FIELDS)
    fields.extend(field for field in OPTIONAL_DOCUMENT_FIELDS if field in existing_columns)
    return ", ".join(fields)


def fetch_document(doc_id: str) -> Optional[sqlite3.Row]:
    conn = get_archive_connection()
    try:
        select_fields = get_document_select_fields(conn)
        return conn.execute(
            f"""
            SELECT {select_fields}
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
    finally:
        conn.close()


def fetch_random_document() -> Optional[sqlite3.Row]:
    conn = get_archive_connection()
    try:
        select_fields = get_document_select_fields(conn)
        return conn.execute(
            f"""
            SELECT {select_fields}
            FROM documents
            WHERE pdf_path IS NOT NULL
              AND pdf_path != ''
            ORDER BY RANDOM()
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()


def fetch_year_range() -> Optional[sqlite3.Row]:
    conn = get_archive_connection()
    try:
        return conn.execute(
            """
            SELECT
                MIN(CAST(year AS INTEGER)) AS min_year,
                MAX(CAST(year AS INTEGER)) AS max_year
            FROM documents
            WHERE year GLOB '[0-9][0-9][0-9][0-9]'
            """
        ).fetchone()
    finally:
        conn.close()


def fetch_documents(doc_ids: Iterable[str]) -> List[sqlite3.Row]:
    doc_ids = list(doc_ids)
    if not doc_ids:
        return []

    placeholders = ",".join("?" for _ in doc_ids)
    conn = get_archive_connection()
    try:
        select_fields = get_document_select_fields(conn)
        return conn.execute(
            f"""
            SELECT {select_fields}
            FROM documents
            WHERE doc_id IN ({placeholders})
            ORDER BY date, doc_id
            """,
            doc_ids,
        ).fetchall()
    finally:
        conn.close()


def fetch_chunk(chunk_id: str) -> Optional[sqlite3.Row]:
    conn = get_chunks_connection()
    try:
        return conn.execute(
            """
            SELECT chunk_id, doc_id, chunk_index, year, date, source_text_path, text, word_count
            FROM chunks
            WHERE chunk_id = ?
            """,
            (chunk_id,),
        ).fetchone()
    finally:
        conn.close()
