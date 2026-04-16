"""
Embed chunked archive text for semantic retrieval.

This script reads chunk rows from chunks.db, generates vector embeddings using
either sentence-transformers/all-MiniLM-L6-v2, OpenAI's text-embedding-3-small, 
or both, and writes the resulting embedding arrays, metadata files, optional FAISS 
indices, and configuration artifacts to backend-specific output directories.

Notes: 
A FAISS (Facebook AI Similarity Search) index is a searchable container of embedding 
vectors optimized for nearest-neighbor lookup. Instead of comparing query vector against 
every chunk vector manually, all chunk vectors are stored in a FAISS index and asking 
FAISS for nearest matches.

`index = faiss.IndexFlatIP(embeddings.shape[1])`

Later in retrieval, backend/search_vector.py loads the saved index and does: 
`scores, indices = index.search(query_vector, requested_k)`
This takes the embedded query, finds the top k nearest chunk vectors, and returns
their scores and positions.
"""

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
from tqdm import tqdm

import os
from dotenv import load_dotenv

load_dotenv()  # This loads the variables from .env


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
CHUNKS_DB = OUTPUT_DIR / "metadata" / "chunks.db"

SENTENCE_TRANSFORMERS_DIR = OUTPUT_DIR / "embeddings_sentencetransformers"
OPENAI_DIR = OUTPUT_DIR / "embeddings_openai"

DEFAULT_ST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
DEFAULT_BATCH_SIZE = 64

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
print(OPENAI_API_KEY)
MAX_OPENAI_RETRIES = 8

# Parse command-line options that control which chunk database, backend, model, batch size, and row limit to use.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed chunked archive text with one or more backends.")
    parser.add_argument("--chunks-db", default=str(CHUNKS_DB), help="Path to chunks.db")
    parser.add_argument(
        "--backend",
        choices=["sentence-transformers", "openai", "both"],
        default="sentence-transformers",
        help="Which embedding backend to run.",
    )
    parser.add_argument(
        "--st-model",
        default=DEFAULT_ST_MODEL,
        help="SentenceTransformer model name.",
    )
    parser.add_argument(
        "--openai-model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI embedding model name.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Embedding batch size")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for testing")
    return parser.parse_args()


# Load chunk rows from chunks.db in chronological order, with an optional limit for testing.
def load_chunks(db_path: Path, limit: Optional[int]) -> List[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT chunk_id, doc_id, chunk_index, year, date, source_text_path, text, word_count
            FROM chunks
            ORDER BY date, doc_id, chunk_index
        """
        params = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()

# Yield the chunk rows in fixed-size batches for more efficient embedding requests.
def batched(rows: List[sqlite3.Row], batch_size: int):
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]


# Ensure the embedding output directory exists before writing artifacts into it.
def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# Write chunk-level metadata alongside the embeddings so vector results can be mapped back to source chunks.
def write_metadata(rows: List[sqlite3.Row], output_dir: Path) -> Path:
    metadata_path = output_dir / "text_metadata.jsonl"
    with metadata_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    {
                        "chunk_id": row["chunk_id"],
                        "doc_id": row["doc_id"],
                        "chunk_index": row["chunk_index"],
                        "year": row["year"],
                        "date": row["date"],
                        "source_text_path": row["source_text_path"],
                        "word_count": row["word_count"],
                    }
                )
                + "\n"
            )
    return metadata_path


# Build and save a FAISS inner-product index for the embeddings when faiss is available.
def maybe_write_faiss(embeddings: np.ndarray, output_dir: Path) -> Optional[Path]:
    try:
        import faiss  # type: ignore
    except Exception:
        return None

    faiss_path = output_dir / "text_faiss.index"
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings.astype("float32"))
    faiss.write_index(index, str(faiss_path))
    return faiss_path

# Save the embedding matrix, metadata, optional FAISS index, and backend configuration for downstream retrieval.
def write_outputs(
    rows: List[sqlite3.Row],
    embeddings: np.ndarray,
    output_dir: Path,
    config: dict,
) -> None:
    ensure_output_dir(output_dir)

    embeddings_path = output_dir / "text_embeddings.npy"
    metadata_path = write_metadata(rows, output_dir)
    np.save(embeddings_path, embeddings.astype("float32"))
    faiss_path = maybe_write_faiss(embeddings, output_dir)

    config["artifacts"] = {
        "embeddings_npy": str(embeddings_path),
        "metadata_jsonl": str(metadata_path),
        "faiss_index": str(faiss_path) if faiss_path is not None else None,
    }

    config_path = output_dir / "text_embedding_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print("Vectors: {}".format(embeddings_path))
    print("Metadata: {}".format(metadata_path))
    if faiss_path is not None:
        print("FAISS index: {}".format(faiss_path))
    else:
        print("FAISS index not written because faiss is not installed.")
    print("Config: {}".format(config_path))


# Generate normalized embeddings for all chunks using a local sentence-transformers model and write the resulting artifacts.
def run_sentence_transformers(
    rows: List[sqlite3.Row],
    model_name: str,
    batch_size: int,
) -> None:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "sentence-transformers is required. Install it before running this backend."
        ) from exc

    model = SentenceTransformer(model_name)
    all_embeddings = []
    batches = list(batched(rows, batch_size))

    for batch in tqdm(
        batches,
        total=len(batches),
        desc="Embedding chunks (sentence-transformers)",
        unit="batch",
    ):
        texts = [row["text"] for row in batch]
        batch_embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        all_embeddings.append(batch_embeddings.astype("float32"))

    embeddings = np.vstack(all_embeddings)
    write_outputs(
        rows=rows,
        embeddings=embeddings,
        output_dir=SENTENCE_TRANSFORMERS_DIR,
        config={
            "backend": "sentence-transformers",
            "model_name": model_name,
            "batch_size": batch_size,
            "num_chunks": len(rows),
            "embedding_dim": int(embeddings.shape[1]),
            "normalized": True,
        },
    )


# Generate normalized embeddings for all chunks using the OpenAI embeddings API with retry handling and write the artifacts.
def run_openai(
    rows: List[sqlite3.Row],
    model_name: str,
    batch_size: int,
) -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception as exc:
        raise RuntimeError("python-dotenv is required for loading .env files.") from exc

    try:
        from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError  # type: ignore
    except Exception as exc:
        raise RuntimeError("openai is required before running the OpenAI backend.") from exc

    load_dotenv(ROOT / ".env")
    client = OpenAI(api_key=OPENAI_API_KEY)

    all_embeddings = []
    batches = list(batched(rows, batch_size))

    progress = tqdm(
        batches,
        total=len(batches),
        desc="Embedding chunks (OpenAI)",
        unit="batch",
    )
    for batch in progress:
        texts = [row["text"] for row in batch]
        batch_embeddings = None

        for attempt in range(MAX_OPENAI_RETRIES):
            try:
                response = client.embeddings.create(model=model_name, input=texts)
                batch_embeddings = np.array(
                    [item.embedding for item in response.data],
                    dtype="float32",
                )
                break
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                wait_seconds = min(2 ** attempt, 30)
                progress.set_postfix_str(
                    "retrying in {}s after {}".format(wait_seconds, exc.__class__.__name__)
                )
                time.sleep(wait_seconds)

        if batch_embeddings is None:
            raise RuntimeError(
                "OpenAI embedding failed after {} retries for batch starting with chunk {}".format(
                    MAX_OPENAI_RETRIES,
                    batch[0]["chunk_id"],
                )
            )

        norms = np.linalg.norm(batch_embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        batch_embeddings = batch_embeddings / norms
        all_embeddings.append(batch_embeddings)

    embeddings = np.vstack(all_embeddings)
    write_outputs(
        rows=rows,
        embeddings=embeddings,
        output_dir=OPENAI_DIR,
        config={
            "backend": "openai",
            "model_name": model_name,
            "batch_size": batch_size,
            "num_chunks": len(rows),
            "embedding_dim": int(embeddings.shape[1]),
            "normalized": True,
        },
    )


def main() -> None:
    args = parse_args()
    db_path = Path(args.chunks_db)

    if not db_path.exists():
        raise FileNotFoundError("Missing chunks database: {}".format(db_path))

    rows = load_chunks(db_path, args.limit)
    if not rows:
        raise RuntimeError("No chunk rows found in chunks.db")

    print("Loaded {} chunks from {}".format(len(rows), db_path))

    if args.backend in ("sentence-transformers", "both"):
        run_sentence_transformers(rows, model_name=args.st_model, batch_size=args.batch_size)

    if args.backend in ("openai", "both"):
        run_openai(rows, model_name=args.openai_model, batch_size=args.batch_size)


# Orchestrate the embedding pipeline by loading chunk rows and running one or both configured embedding backends.
if __name__ == "__main__":
    main()
