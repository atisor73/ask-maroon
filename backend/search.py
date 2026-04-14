from typing import Dict, List

from search_fts import search_fts
from search_vector import search_vector


def _merge_results(vector_results: List[dict], fts_results: List[dict]) -> List[dict]:
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
            }
            continue

        combined_row = combined[chunk_id]
        combined_row["fts_score"] = row["score"]
        combined_row["fts_rank"] = rank
        combined_row["combined_score"] += 0.15 * boost
        combined_row["retrieval_methods"].append("fts")

    return sorted(combined.values(), key=lambda row: row["combined_score"], reverse=True)


def search(query: str, limit: int = 10, vector_k: int = 50, fts_k: int = 25) -> List[dict]:
    vector_results = search_vector(query, limit=vector_k)
    fts_results = search_fts(query, limit=fts_k)
    merged = _merge_results(vector_results, fts_results)
    return merged[:limit]


if __name__ == "__main__":
    import json
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "student protests on campus"
    backend = sys.argv[2] if len(sys.argv) > 2 else "sentence-transformers"
    vector_results = search_vector(query, limit=50, backend=backend)
    fts_results = search_fts(query, limit=25)
    results = _merge_results(vector_results, fts_results)[:5]
    print(json.dumps(results[:5], indent=2))
