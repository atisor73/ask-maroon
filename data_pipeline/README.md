# data_pipeline/

This folder contains the preprocessing pipeline that turns raw Chicago Maroon archive materials into structured, searchable retrieval data. The pipeline moves from scraped metadata and extracted plain text to cleaned text, chunk-level search corpora, and embedding artifacts used by the backend search system.

# Methodology notes
Individual files contain docstrings that go into more detail on their methodology.

- Scraping URL:
  The archive was scraped from the Chicago Maroon archive site and associated source links recorded in the metadata output.

- Text cleaning:
  Raw extracted `.txt` files are cleaned before chunking to repair common OCR and extraction artifacts such as broken hyphenation across line breaks, ligatures, missing spaces, replacement characters, and some glued-together words.

- Chunking:
  Text is chunked by approximate word count rather than model tokens or character count.
  Chunks target 500 words with 75 words of overlap between adjacent chunks.
  The chunker tries to preserve paragraph boundaries first, then sentence boundaries, and only falls back to fixed word slices when necessary.

- Embeddings:
  Chunk text is embedded after chunking, using either `sentence-transformers/all-MiniLM-L6-v2`, OpenAI `text-embedding-3-small`, or both, depending on the pipeline run.
  Embedding outputs include vector arrays, metadata files, and optional FAISS indices for semantic retrieval.

- Metadata indexing:
  Document-level metadata such as `doc_id`, date, title, file paths, OCR/text status, and page counts are written into SQLite and parquet outputs for downstream use.

- Search artifacts:
  The pipeline produces the structured assets used by the backend search app, including cleaned text, `chunks.db`, metadata databases, embedding matrices, and FAISS indices.


# Outputs
`run.sh` runs files sequentially. However, recommendation is to run scripts one at a time in case of failure and checking for correct outputs.

`scraper_0.py`
- output/links.json: document links 
- output/failed_pages.json: failed pages to retrieve document links (page contains a set of documents)

`scraper_1.py`
- output/pdf-links.json: pdf links within document links

`scraper_2.py`
- output/pdfs/...: pdf of old archives
- can also run in R2 upload mode from Hetzner using temporary local files only

`clean_text.py`
- output/plain_text_cleaned/

`build_metadata_index.py`
- output/metadata/archive.db
- output/metadata/docs.parquet

`chunk_text.py`
- output/metadata/chunks.db

`embed_text.py`
- output/embeddings_sentencetransformers/
- output/embeddings_openai/
```
python3 embed_text.py --backend sentence-transformers
python3 embed_text.py --backend openai
python3 embed_text.py --backend both
python3 embed_text.py --backend both --limit 200
```

`map_chunks_to_pages.py`
- ouptut/metadata/chunks.db
- ouptut/page_text_cache/*

`copy_output_to_r2.py`
- uploads all files under `output/` to Cloudflare R2 recursively
- skips existing bucket objects by default

# R2 scraping mode
If Hetzner does not have enough disk to store the whole corpus locally, `scraper_2.py` can now scrape the same source URLs and upload directly to Cloudflare R2.

Required environment variables in `.env`:
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET`
- optional: `R2_ENDPOINT_URL`

Bucket vs prefix:
- If you want objects stored under `s3://ask-maroon-dev/archive/...`, then set `R2_BUCKET=ask-maroon-dev`
- and use `--r2-prefix archive`
- `archive` is already the default prefix in these scripts

Example:
```bash
python3 scraper_2.py --mode r2 --r2-prefix maroon-archives --temp-dir /tmp/maroon-cache
```

Behavior:
- In `--mode r2`, each PDF/text file is downloaded to a temporary local path, uploaded to R2, then deleted locally.
- Existing R2 objects are skipped by default using an object existence check.
- Pass `--force` if you intentionally want to overwrite objects already in the bucket.

Bulk upload an existing `output/` tree:
```bash
python3 copy_output_to_r2.py --r2-prefix maroon-archives
```
