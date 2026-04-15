import html
import re
from typing import Dict, List, Optional

try:
    from .db import fetch_documents
    from .search_fts import search_fts
    from .search_vector import search_vector
except ImportError:
    from db import fetch_documents
    from search_fts import search_fts
    from search_vector import search_vector


SNIPPET_LENGTH = 280
WINDOW_WORDS = 24
WINDOW_STRIDE = 12
STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "among",
    "and",
    "are",
    "because",
    "been",
    "being",
    "between",
    "both",
    "during",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "over",
    "said",
    "some",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
}


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


def _stem_token(token: str) -> str:
    token = token.lower()
    for suffix in ("ingly", "edly", "ing", "edly", "edly", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _content_terms(query: str) -> List[str]:
    return [term for term in _query_terms(query) if term not in STOPWORDS]


def _sentence_candidates(text: str) -> List[str]:
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return []

    sentence_like = [
        part.strip()
        for part in re.split(r"(?<=[.!?;:])\s+", clean_text)
        if part.strip()
    ]

    candidates = [part for part in sentence_like if len(part) >= 35]

    words = clean_text.split()
    if len(words) > WINDOW_WORDS:
        for start in range(0, len(words), WINDOW_STRIDE):
            window = " ".join(words[start : start + WINDOW_WORDS]).strip()
            if len(window) >= 35:
                candidates.append(window)
            if start + WINDOW_WORDS >= len(words):
                break

    # Preserve order while removing duplicates.
    seen = set()
    deduped = []
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _segment_score(segment: str, query: str) -> float:
    query_terms = _content_terms(query)
    if not query_terms:
        return 0.0

    segment_terms = re.findall(r"[A-Za-z0-9]+", segment.lower())
    if not segment_terms:
        return 0.0

    query_stems = [_stem_token(term) for term in query_terms]
    segment_stems = [_stem_token(term) for term in segment_terms]
    segment_text = segment.lower()

    exact_hits = sum(1 for term in query_terms if re.search(r"\b{}\b".format(re.escape(term)), segment_text))

    stem_hits = 0
    for query_stem in query_stems:
        if any(
            seg_stem == query_stem
            or seg_stem.startswith(query_stem)
            or query_stem.startswith(seg_stem)
            for seg_stem in segment_stems
        ):
            stem_hits += 1

    phrase_bonus = 0.0
    for first, second in zip(query_terms, query_terms[1:]):
        if "{} {}".format(first, second) in segment_text:
            phrase_bonus += 0.6

    density_bonus = min(len(segment_terms), WINDOW_WORDS) / float(WINDOW_WORDS)
    return (1.8 * exact_hits) + stem_hits + phrase_bonus + (0.15 * density_bonus)


def _best_focus_phrases(text: str, query: str, max_phrases: int = 2) -> List[str]:
    scored = []
    for candidate in _sentence_candidates(text):
        score = _segment_score(candidate, query)
        if score <= 0:
            continue
        scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in scored[:max_phrases]]


def _collect_spans(text: str, query: str, focus_phrases: List[str]) -> List[tuple]:
    spans = []

    for phrase in focus_phrases:
        if not phrase:
            continue
        for match in re.finditer(re.escape(phrase), text, flags=re.IGNORECASE):
            spans.append((match.start(), match.end(), "semantic"))

    for term in sorted(_query_terms(query), key=len, reverse=True):
        for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
            spans.append((match.start(), match.end(), "exact"))

    if not spans:
        return []

    priority = {"semantic": 0, "exact": 1}
    spans.sort(key=lambda item: (item[0], item[1] - item[0], priority[item[2]]))

    merged = []
    last_end = -1
    for start, end, kind in spans:
        if start < last_end:
            continue
        merged.append((start, end, kind))
        last_end = end

    return merged


def _render_highlight_html(text: str, query: str, focus_phrases: List[str]) -> str:
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return ""

    spans = _collect_spans(clean_text, query, focus_phrases)
    if not spans:
        return html.escape(clean_text)

    parts = []
    cursor = 0
    for start, end, kind in spans:
        if cursor < start:
            parts.append(html.escape(clean_text[cursor:start]))

        klass = "semantic-mark" if kind == "semantic" else ""
        class_attr = ' class="{}"'.format(klass) if klass else ""
        parts.append(
            "<mark{}>{}</mark>".format(class_attr, html.escape(clean_text[start:end]))
        )
        cursor = end

    if cursor < len(clean_text):
        parts.append(html.escape(clean_text[cursor:]))

    return "".join(parts)


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
    focus_phrases = _best_focus_phrases(clean_text, query, max_phrases=1)
    match = None
    for term in terms:
        match = re.search(re.escape(term), clean_text, flags=re.IGNORECASE)
        if match:
            break

    if match is None and focus_phrases:
        match = re.search(re.escape(focus_phrases[0]), clean_text, flags=re.IGNORECASE)

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

    snippet_html = _render_highlight_html(snippet, query, focus_phrases)
    full_text_html = _render_highlight_html(clean_text, query, _best_focus_phrases(clean_text, query))

    return {
        "snippet": snippet,
        "snippet_html": snippet_html,
        "full_text_html": full_text_html,
    }


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
                "combined_score": 0.10 * boost,
                "retrieval_methods": ["fts"],
                "vector_rank": None,
                "fts_rank": rank,
                "embedding_backend": None,
            }
            continue

        combined_row = combined[chunk_id]
        combined_row["fts_score"] = row["score"]
        combined_row["fts_rank"] = rank
        combined_row["combined_score"] += 0.10 * boost
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
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> dict:
    """
    Main backend search entrypoint.

    Returns both:
    - chunk-ranked results for fine-grained retrieval/debugging
    - document-grouped results for the frontend list view
    """
    vector_results = search_vector(
        query,
        limit=vector_k,
        backend=backend,
        start_year=start_year,
        end_year=end_year,
    )
    fts_results = search_fts(
        query,
        limit=fts_k,
        start_year=start_year,
        end_year=end_year,
    )
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
