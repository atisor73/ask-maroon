from typing import List

from db import get_chunks_connection


def search_fts(query: str, limit: int = 10) -> List[dict]:
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
            (query, limit),
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
