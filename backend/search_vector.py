import json
from pathlib import Path
from typing import Dict, List

import numpy as np

from db import OUTPUT_DIR, get_chunks_connection

# Change directory to change model
SENTENCE_TRANSFORMERS_DIR = OUTPUT_DIR / "embeddings_sentencetransformers"
OPENAI_DIR = OUTPUT_DIR / "embeddings_openai"
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_OPENAI_MODEL_NAME = "text-embedding-3-small"

_RESOURCE_CACHE = {}


def _load_metadata(metadata_path: Path) -> List[dict]:
    with metadata_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _load_index(index_path: Path):
    import faiss  # type: ignore

    return faiss.read_index(str(index_path))


def _load_model(model_name: str):
    from sentence_transformers import SentenceTransformer  # type: ignore

    return SentenceTransformer(model_name)


def _get_resources(
    backend: str,
    embeddings_dir: Path,
    model_name: str,
):
    cache_key = (backend, str(embeddings_dir), model_name)
    if cache_key in _RESOURCE_CACHE:
        return _RESOURCE_CACHE[cache_key]

    index = _load_index(embeddings_dir / "text_faiss.index")
    metadata = _load_metadata(embeddings_dir / "text_metadata.jsonl")

    if backend == "sentence-transformers":
        model = _load_model(model_name)
    elif backend == "openai":
        from dotenv import load_dotenv  # type: ignore
        from openai import OpenAI  # type: ignore

        load_dotenv(OUTPUT_DIR.parent / ".env")
        model = OpenAI()
    else:
        raise ValueError("Unsupported backend: {}".format(backend))

    _RESOURCE_CACHE[cache_key] = (index, metadata, model)
    return _RESOURCE_CACHE[cache_key]


def _embed_query(query: str, backend: str, model, model_name: str) -> np.ndarray:
    if backend == "sentence-transformers":
        return model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")

    if backend == "openai":
        response = model.embeddings.create(model=model_name, input=[query])
        vector = np.array([response.data[0].embedding], dtype="float32")
        norms = np.linalg.norm(vector, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vector / norms

    raise ValueError("Unsupported backend: {}".format(backend))


def _fetch_chunks_by_ids(chunk_ids: List[str]) -> Dict[str, dict]:
    if not chunk_ids:
        return {}

    placeholders = ",".join("?" for _ in chunk_ids)
    conn = get_chunks_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT chunk_id, doc_id, chunk_index, year, date, source_text_path, text, word_count
            FROM chunks
            WHERE chunk_id IN ({placeholders})
            """,
            chunk_ids,
        ).fetchall()
    finally:
        conn.close()

    return {row["chunk_id"]: dict(row) for row in rows}


def search_vector(
    query: str,
    limit: int = 10,
    backend: str = "sentence-transformers",
    embeddings_dir: Path = None,
    model_name: str = None,
) -> List[dict]:
    if embeddings_dir is None:
        embeddings_dir = SENTENCE_TRANSFORMERS_DIR if backend == "sentence-transformers" else OPENAI_DIR
    if model_name is None:
        model_name = DEFAULT_MODEL_NAME if backend == "sentence-transformers" else DEFAULT_OPENAI_MODEL_NAME

    index, metadata, model = _get_resources(
        backend=backend,
        embeddings_dir=embeddings_dir,
        model_name=model_name,
    )

    query_vector = _embed_query(query, backend=backend, model=model, model_name=model_name)

    scores, indices = index.search(query_vector, limit)
    hit_metadata = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        row = dict(metadata[idx])
        row["score"] = float(score)
        hit_metadata.append(row)

    chunk_map = _fetch_chunks_by_ids([row["chunk_id"] for row in hit_metadata])

    results = []
    for row in hit_metadata:
        chunk_row = chunk_map.get(row["chunk_id"])
        if chunk_row is None:
            continue
        results.append(
            {
                **chunk_row,
                "score": row["score"],
                "retrieval_method": "vector",
                "embedding_backend": backend,
            }
        )

    return results


if __name__ == "__main__":
    import json as _json
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "student protests on campus"
    backend = sys.argv[2] if len(sys.argv) > 2 else "sentence-transformers"
    results = search_vector(query, backend=backend)
    print(_json.dumps(results[:3], indent=2))
