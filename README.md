# data_pipeline/

`run.sh` runs files sequentially

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
```
python3 embed_text.py --backend sentence-transformers
python3 embed_text.py --backend openai
python3 embed_text.py --backend both
python3 embed_text.py --backend both --limit 200
```

### To-do's: fix / adjust PDF ocr to locate blocks within pdf?


# backend/
Testing query:
- test_backend.ipynb contains code that runs a query, calling search_fts.py and search_vector.py functions


Testing API:
```
uvicorn backend.app:app --reload
http://127.0.0.1:8000/health
http://127.0.0.1:8000/search?q=student%20protests&backend=openai
http://127.0.0.1:8000/search?q=student%20protests&backend=sentence-transformers
```





# frontend/
Start backend: `uvicorn backend.app:app --reload`
Serve frontend: `python3 -m http.server 3000`

Navigate: http://127.0.0.1:3000/frontend/
Backend docs: http://127.0.0.1:8000/docs



# test queries
crimes related to bikes cycling cyclists bicycles
articles related to haircuts, hairstyles, hair


# GPT recommendations: 

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


Keep current retrieval pipeline
OCR text
chunks
embeddings
search UI

Add page mapping next
per-page text extraction
fuzzy match chunk to page
open PDF to that page