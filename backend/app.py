from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

try:
    from .db import PROJECT_ROOT, fetch_document, fetch_random_document, fetch_year_range
    from .schemas import SearchMetadataResponse, SearchResponse
    from .search import search
except ImportError:
    from db import PROJECT_ROOT, fetch_document, fetch_random_document, fetch_year_range
    from schemas import SearchMetadataResponse, SearchResponse
    from search import search


app = FastAPI(title="Maroon Archive Search API")

# Allow the deployed Cloudflare Pages frontend plus local dev servers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ask-maroon.pages.dev",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def run_search_with_fallback(
    query: str,
    backend: str,
    limit: int,
    vector_k: int,
    fts_k: int,
    start_year: Optional[int],
    end_year: Optional[int],
    search_mode: str,
    sample_top_n: int,
    temperature: float,
) -> dict:
    """
    Try the requested vector backend first.

    If OpenAI fails at query time, we fall back to sentence-transformers so the
    frontend still gets a usable result set. The API response records that the
    fallback happened.
    """
    try:
        result = search(
            query=query,
            limit=limit,
            vector_k=vector_k,
            fts_k=fts_k,
            backend=backend,
            start_year=start_year,
            end_year=end_year,
            search_mode=search_mode,
            sample_top_n=sample_top_n,
            temperature=temperature,
        )
        result["requested_backend"] = backend
        result["used_fallback"] = False
        result["fallback_reason"] = None
        return result
    except Exception as exc:
        if backend != "openai":
            raise

        fallback_result = search(
            query=query,
            limit=limit,
            vector_k=vector_k,
            fts_k=fts_k,
            backend="sentence-transformers",
            start_year=start_year,
            end_year=end_year,
            search_mode=search_mode,
            sample_top_n=sample_top_n,
            temperature=temperature,
        )
        fallback_result["requested_backend"] = backend
        fallback_result["used_fallback"] = True
        fallback_result["fallback_reason"] = str(exc)
        return fallback_result


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/search", response_model=SearchResponse)
def search_endpoint(
    q: str = Query(..., description="User search query"),
    backend: str = Query(
        "sentence-transformers",
        pattern="^(sentence-transformers|openai)$",
        description="Which vector backend to use",
    ),
    limit: int = Query(10, ge=1, le=50),
    vector_k: int = Query(50, ge=1, le=500),
    fts_k: int = Query(25, ge=1, le=200),
    start_year: Optional[int] = Query(None, ge=1000, le=9999),
    end_year: Optional[int] = Query(None, ge=1000, le=9999),
    search_mode: str = Query("greedy", pattern="^(greedy|sample)$"),
    sample_top_n: int = Query(100, ge=25, le=100),
    temperature: float = Query(1.0, ge=0.1, le=10.0),
):
    if start_year is not None and end_year is not None and start_year > end_year:
        raise HTTPException(status_code=400, detail="start_year must be less than or equal to end_year")

    return run_search_with_fallback(
        query=q,
        backend=backend,
        limit=limit,
        vector_k=vector_k,
        fts_k=fts_k,
        start_year=start_year,
        end_year=end_year,
        search_mode=search_mode,
        sample_top_n=sample_top_n,
        temperature=temperature,
    )


@app.get("/search-metadata", response_model=SearchMetadataResponse)
def search_metadata_endpoint():
    row = fetch_year_range()
    if row is None or row["min_year"] is None or row["max_year"] is None:
        raise HTTPException(status_code=404, detail="No year metadata available")
    return {"min_year": row["min_year"], "max_year": row["max_year"]}


@app.get("/document/{doc_id}")
def document_endpoint(doc_id: str) -> dict:
    row = fetch_document(doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


@app.get("/random-document")
def random_document_endpoint() -> dict:
    """
    Return one random issue so the frontend can support exploratory browsing.
    """
    row = fetch_random_document()
    if row is None:
        raise HTTPException(status_code=404, detail="No documents available")
    return dict(row)


@app.get("/pdf/{doc_id}")
def pdf_endpoint(doc_id: str):
    """
    Serve the original PDF so the frontend can open the source issue.

    This is a simple first step. Later, the frontend can use page numbers or
    coordinates to jump to more precise locations in the PDF.
    """
    row = fetch_document(doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    pdf_path = Path(row["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="{}"'.format(pdf_path.name)},
    )


@app.get("/")
def root() -> dict:
    return {
        "message": "Maroon Archive Search API",
        "project_root": str(PROJECT_ROOT),
        "routes": ["/health", "/search", "/document/{doc_id}", "/random-document", "/pdf/{doc_id}"],
    }
