from typing import List, Optional

from pydantic import BaseModel


class ChunkResult(BaseModel):
    # Chunk-level result returned from hybrid retrieval.
    chunk_id: str
    doc_id: str
    chunk_index: int
    year: Optional[str] = None
    date: Optional[str] = None
    page_number: Optional[int] = None
    page_match_score: Optional[float] = None
    source_text_path: Optional[str] = None
    text: str
    snippet: str
    snippet_html: str
    full_text_html: str
    word_count: int
    score: float
    vector_score: Optional[float] = None
    fts_score: Optional[float] = None
    combined_score: float
    retrieval_methods: List[str]
    vector_rank: Optional[int] = None
    fts_rank: Optional[int] = None
    embedding_backend: Optional[str] = None


class DocumentResult(BaseModel):
    # Document-level grouping for the frontend list view.
    doc_id: str
    doc_score: float
    best_chunk_id: str
    best_chunk_score: float
    chunk_count: int
    year: Optional[str] = None
    date: Optional[str] = None
    title: Optional[str] = None
    pdf_path: Optional[str] = None
    text_path: Optional[str] = None
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    plain_text_url: Optional[str] = None
    chunks: List[ChunkResult]


class SearchResponse(BaseModel):
    # Final API response from /search.
    query: str
    requested_backend: str
    vector_backend: str
    used_fallback: bool
    fallback_reason: Optional[str] = None
    chunk_results: List[ChunkResult]
    document_results: List[DocumentResult]
