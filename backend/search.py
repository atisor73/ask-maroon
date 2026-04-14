import html
import re
from typing import Dict, List

try:
    from .db import fetch_documents
    from .search_fts import search_fts
    from .search_vector import search_vector
except ImportError:
    from db import fetch_documents
    from search_fts import search_fts
    from search_vector import search_vector


SNIPPET_LENGTH = 280


def _query_terms(query: str) -> List[str]:
    """
    Extract basic query terms for snippet generation/highlighting.

    We keep this intentionally simple for now:
    - lowercase
    - alphanumeric tokens
    - ignore very short words
    """
    terms = re.findall(r"[A-Za-z0-9]+", query.lower())
    return [term for term in terms if len(term) >= 3]


def _build_snippet(text: str, query: str, snippet_length: int = SNIPPET_LENGTH) -> Dict[str, str]:
    """
    Create a short preview snippet and HTML-highlighted version.

    Strategy:
    - Try to center the snippet around the first literal query-term match.
    - If no literal term exists, fall back to the start of the chunk.
    - Return both plain text and simple <mark>-wrapped HTML.
    """
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return {"snippet": "", "snippet_html": ""}

    terms = _query_terms(query)
    match = None
    for term in terms:
        match = re.search(re.escape(term), clean_text, flags=re.IGNORECASE)
        if match:
            break

    if match:
        center = (match.start() + match.end()) // 2
        start = max(0, center - (snippet_length // 2))
        end = min(len(clean_text), start + snippet_length)
        start = max(0, end - snippet_length)
    else:
        start = 0
        end = min(len(clean_text), snippet_length)

    snippet = clean_text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(clean_text):
        snippet = snippet + "..."

    snippet_html = html.escape(snippet)
    for term in sorted(terms, key=len, reverse=True):
        snippet_html = re.sub(
            re.escape(html.escape(term)),
            lambda m: "<mark>{}</mark>".format(m.group(0)),
            snippet_html,
            flags=re.IGNORECASE,
        )

    return {"snippet": snippet, "snippet_html": snippet_html}


def _merge_results(vector_results: List[dict], fts_results: List[dict]) -> List[dict]:
    """
    Merge chunk-level vector and FTS hits into one ranked list.

    Design choice:
    - Vector search is the main recall signal.
    - FTS contributes a small boost when exact terms match.
    - We keep both raw component scores around for debugging/UI display.
    """
    combined: Dict[str, dict] = {}

    for rank, row in enumerate(vector_results):
        chunk_id = row["chunk_id"]
        combined[chunk_id] = {
            **row,
            "vector_score": row["score"],
            "fts_score": None,
            "combined_score": row["score"],
            "retrieval_methods": ["vector"],
            "vector_rank": rank,
            "fts_rank": None,
        }

    for rank, row in enumerate(fts_results):
        chunk_id = row["chunk_id"]

        # We do not compare bm25 directly to cosine similarity because the scales differ.
        # Instead, we convert FTS rank into a small monotonic boost.
        boost = 1.0 / (rank + 1)

        if chunk_id not in combined:
            combined[chunk_id] = {
                **row,
                "vector_score": None,
                "fts_score": row["score"],
                "combined_score": 0.15 * boost,
                "retrieval_methods": ["fts"],
                "vector_rank": None,
                "fts_rank": rank,
                "embedding_backend": None,
            }
            continue

        combined_row = combined[chunk_id]
        combined_row["fts_score"] = row["score"]
        combined_row["fts_rank"] = rank
        combined_row["combined_score"] += 0.15 * boost
        combined_row["retrieval_methods"].append("fts")

    return sorted(combined.values(), key=lambda row: row["combined_score"], reverse=True)


def _group_results_by_document(chunk_results: List[dict], doc_limit: int) -> List[dict]:
    """
    Build a document-level view while preserving chunk-level evidence.

    Document score is based mostly on the best chunk, with a small bonus if the
    document has multiple relevant chunks near the top.
    """
    grouped: Dict[str, dict] = {}

    for row in chunk_results:
        doc_id = row["doc_id"]
        if doc_id not in grouped:
            grouped[doc_id] = {
                "doc_id": doc_id,
                "doc_score": row["combined_score"],
                "best_chunk_id": row["chunk_id"],
                "best_chunk_score": row["combined_score"],
                "chunk_count": 0,
                "chunks": [],
            }

        doc_entry = grouped[doc_id]
        doc_entry["chunks"].append(row)
        doc_entry["chunk_count"] += 1

        if row["combined_score"] > doc_entry["best_chunk_score"]:
            doc_entry["best_chunk_score"] = row["combined_score"]
            doc_entry["best_chunk_id"] = row["chunk_id"]

        # Reward documents that surface more than one relevant chunk,
        # but keep the best chunk as the dominant signal.
        doc_entry["doc_score"] = max(doc_entry["doc_score"], doc_entry["best_chunk_score"]) + (
            0.03 * (doc_entry["chunk_count"] - 1)
        )

    doc_rows = {row["doc_id"]: dict(row) for row in fetch_documents(grouped.keys())}

    documents = []
    for doc_id, entry in grouped.items():
        doc_row = doc_rows.get(doc_id, {})
        documents.append(
            {
                "doc_id": doc_id,
                "doc_score": entry["doc_score"],
                "best_chunk_id": entry["best_chunk_id"],
                "best_chunk_score": entry["best_chunk_score"],
                "chunk_count": entry["chunk_count"],
                "year": doc_row.get("year"),
                "date": doc_row.get("date"),
                "title": doc_row.get("title"),
                "pdf_path": doc_row.get("pdf_path"),
                "text_path": doc_row.get("text_path"),
                "source_url": doc_row.get("source_url"),
                "pdf_url": doc_row.get("pdf_url"),
                "plain_text_url": doc_row.get("plain_text_url"),
                "chunks": entry["chunks"],
            }
        )

    documents.sort(key=lambda row: row["doc_score"], reverse=True)
    return documents[:doc_limit]


def search(
    query: str,
    limit: int = 10,
    vector_k: int = 50,
    fts_k: int = 25,
    backend: str = "sentence-transformers",
) -> dict:
    """
    Main backend search entrypoint.

    Returns both:
    - chunk-ranked results for fine-grained retrieval/debugging
    - document-grouped results for the frontend list view
    """
    vector_results = search_vector(query, limit=vector_k, backend=backend)
    fts_results = search_fts(query, limit=fts_k)
    merged_chunks = _merge_results(vector_results, fts_results)

    for row in merged_chunks:
        row.update(_build_snippet(row["text"], query))

    top_chunks = merged_chunks[:limit]
    top_documents = _group_results_by_document(merged_chunks, doc_limit=limit)

    return {
        "query": query,
        "vector_backend": backend,
        "chunk_results": top_chunks,
        "document_results": top_documents,
    }


if __name__ == "__main__":
    import json
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "student protests on campus"
    backend = sys.argv[2] if len(sys.argv) > 2 else "sentence-transformers"
    results = search(query, backend=backend)
    print(json.dumps(results, indent=2))
