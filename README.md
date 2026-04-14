`run.sh` runs `scraper_0.py`, `scraper_1.py`, `scraper_2.py`

`scraper_0.py`
- output/links.json: document links 
- output/failed_pages.json: failed pages to retrieve document links (page contains a set of documents)

`scraper_1.py`
- output/pdf-links.json: pdf links within document links

`scraper_2.py`
- output/pdfs/...: pdf of old archives

`pdf_to_txt.py`
- converts all pdfs to txt/json? best format for llm?
- how to deal with columnar formatting?

`clean_text.py`
- output/plain_text_cleaned/

`build_metadata_index.py`
- metadata/archive.db
- metadata/docs.parquet

`chunk_text.py`
- metadata/chunks.db

`embed_text.py`
- embeddings_sentencetransformers/
- embeddings_openai/

python3 embed_text.py --backend sentence-transformers
python3 embed_text.py --backend openai
python3 embed_text.py --backend both
python3 embed_text.py --backend both --limit 200

GPT recommendations: 
Layer 1 — Storage
	•	Files (PDF + text)
	•	Your current structure is good

Layer 2 — Index
	•	Metadata table (SQLite / parquet)

Layer 3 — Retrieval
	•	Chunked text + embeddings

Layer 4 — LLM interface
	•	Only sees small, relevant slices

(A) metadata index: docs.parquet  # or sqlite.db
(B) clean text extraction: 	•	Ensure consistent .txt quality
(C) Later: chunk + embed


LLM/RAG is good at retrieving small batches of files (must fit in context length window)

Option i:  Full-text search index - SQLite FTS5
	•	Whoosh
	•	Elasticsearch (heavier)
This is good for searching across entire archive for specific keywords.

Option ii: Embeddings (semantic search)

Now we get closer to your LLM idea—but cheaper and better.

Process:
	1.	Chunk all documents
	2.	Compute embeddings
	3.	Store in vector DB 










==================
1. Chunks vs SQLite Location

Option A: Local SQLite
	•	Pros: Easy, fast, no cloud cost, full control.
	•	Cons: Not inherently distributed; limited by local machine storage if dataset is huge.
	•	Use case: If you have, say, tens of thousands of PDF pages (or text files), local SQLite is perfect.

Option B: Cloud SQLite
	•	Usually, people don’t “upload SQLite” to a cloud service directly. Instead:
	1.	You preprocess and chunk locally.
	2.	Either upload the database file to cloud storage (S3, GDrive) or
	3.	Use a cloud vector database (like Weaviate, Pinecone, or Supabase + pgvector) if you want embeddings searchable in the cloud.

Rule of thumb:
	•	Small to medium datasets → local SQLite + optional FAISS embeddings.
	•	Big datasets or multi-user access → cloud vector database.
