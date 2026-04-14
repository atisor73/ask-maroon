import re
from typing import List

try:
    from .db import get_chunks_connection
except ImportError:
    from db import get_chunks_connection


def _build_safe_match_query(query: str) -> str:
    """
    Convert free-form user text into a conservative FTS5 query.

    Why this exists:
    - SQLite FTS5 MATCH has its own query syntax.
    - Raw punctuation like commas can cause parse errors.
    - For the MVP, we want FTS to behave like a forgiving keyword helper.

    Current strategy:
    - lowercase the query
    - extract alphanumeric terms
    - ignore very short tokens
    - join terms with OR

    Example:
    "crimes, specifically involving bicycles or cyclists"
    ->
    "crimes" OR "specifically" OR "involving" OR "bicycles" OR "cyclists"
    """
    terms = re.findall(r"[A-Za-z0-9]+", query.lower())
    terms = [term for term in terms if len(term) >= 2]
    if not terms:
        return ""
    return " OR ".join('"{}"'.format(term) for term in terms)


def search_fts(query: str, limit: int = 10) -> List[dict]:
    match_query = _build_safe_match_query(query)
    if not match_query:
        return []

    conn = get_chunks_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                c.chunk_id,
                c.doc_id,
                c.chunk_index,
                c.year,
                c.date,
                c.page_number,
                c.page_match_score,
                c.source_text_path,
                c.text,
                c.word_count,
                bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


if __name__ == "__main__":
    import json
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "Robert Hutchins"
    results = search_fts(query)
    print(json.dumps(results[:3], indent=2))
