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

