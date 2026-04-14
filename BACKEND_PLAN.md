
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

# Backend Plan

This project already has the right starting point:

- `output/pdfs/` holds the raw archive source
- `output/plain_text/` holds extracted text

## Short answer

No, you do **not** have to extract images into a separate folder before you can build the first useful search system.

Recommended order:

1. Build document storage + metadata index
2. Build text chunking + SQLite FTS search
3. Build text embeddings
4. Add image extraction only after text retrieval works
5. Add CLIP image/text retrieval after that

Why: text-only retrieval is much simpler, cheaper, and will already answer many archive questions well. Image extraction is worth doing if you want cross-modal search such as:

- "show me photos of protests in the 1960s"
- "find issues with maps, cartoons, or campus scenes"
- "retrieve images related to this text query"

## Recommended directory additions

Keep existing files untouched and add new outputs alongside them:

```text
output/
  pdfs/
  plain_text/
  metadata/
    archive.db
    docs.parquet
  chunks/
    chunks.jsonl
  embeddings/
    text_faiss.index
    text_metadata.parquet
    clip_faiss.index
    clip_metadata.parquet
  extracted_images/
    1902/
    1903/
    ...
```

## Step-by-step plan

### Step 1: Normalize metadata

Goal: one row per document that links PDF, text, and basic identifiers.

Create:

- SQLite table `documents`
- optional `docs.parquet` export for analysis

Suggested fields:

- `doc_id`
- `year`
- `date`
- `title` if available
- `pdf_path`
- `text_path`
- `source_url` if available
- `page_count`
- `ocr_status`
- `text_length`

Why first: everything else depends on a clean mapping between archive items and files.

### Step 2: Clean and chunk text

Goal: produce retrieval-sized chunks instead of embedding whole files.

Approach:

- read each text file
- normalize whitespace and repeated line breaks
- preserve document and page boundaries if possible
- chunk into about `300-800` words with slight overlap

Store each chunk with:

- `chunk_id`
- `doc_id`
- `chunk_index`
- `page_start`
- `page_end`
- `text`
- `year`
- `date`

Why: embeddings and search work much better on chunks than whole newspapers or whole issues.

### Step 3: Add SQLite FTS

Goal: fast keyword and phrase search.

Create:

- `documents` table
- `chunks` table
- `chunks_fts` virtual table with FTS5

Use this for:

- exact phrases
- names
- dates
- narrow filters before semantic retrieval

Why now: this gives you an immediately useful backend even before embeddings.

### Step 4: Add text embeddings

Goal: semantic search over chunk text.

Recommended first pass:

- sentence-transformer for text chunks
- FAISS index for nearest-neighbor search

Store:

- vector index in `output/embeddings/text_faiss.index`
- chunk metadata separately in `text_metadata.parquet` or SQLite

Query flow:

1. embed user query
2. retrieve nearest chunks from FAISS
3. join back to metadata
4. optionally re-rank with keyword matches from SQLite FTS

### Step 5: Decide on image extraction

This should be a **second-phase feature**, not a blocker.

Extract images into `output/extracted_images/` if you want:

- semantic image retrieval
- image + text joint search with CLIP
- downstream captioning or visual analysis

You do **not** need image extraction if your first goal is archive text search or topic analysis.

### Step 6: If extracting images, extract with document linkage

Important: do not just dump loose PNGs into a folder with no provenance.

Each extracted image should map back to:

- `image_id`
- `doc_id`
- `pdf_path`
- `page_number`
- bounding box coordinates
- output image path
- optional nearby caption text

Best practice:

- save cropped image regions as PNGs
- store bounding box metadata in SQLite or JSONL
- keep page-level provenance so you can show the original context later

### Step 7: Add CLIP embeddings

Once images exist, CLIP becomes useful.

Embed:

- all text chunks or image captions
- all extracted image crops

Then store:

- vectors in a FAISS index
- metadata linking each vector to either `chunk` or `image`

This supports:

- text query -> images
- text query -> text
- image query -> similar images

Important note: for text retrieval alone, sentence-transformers will usually outperform CLIP text embeddings. CLIP is most useful when you specifically want shared image-text retrieval.

### Step 8: Add optional image captions/descriptions

This is useful, but optional.

You can generate:

- short captions
- OCR from image regions
- object/scene tags

Then index those captions as text too. This often improves retrieval because:

- CLIP handles visual similarity
- captions improve keyword and semantic matching

## Recommended architecture

### Phase 1 MVP

Build this first:

- existing `pdfs/`
- existing `plain_text/`
- SQLite metadata + FTS
- chunk JSONL or SQLite chunk table
- sentence-transformer embeddings
- FAISS text index

This is enough for:

- keyword search
- semantic text search
- topic tracking over time
- RAG over archive text

### Phase 2 multimodal

Add later:

- `extracted_images/`
- image metadata table
- CLIP embeddings for images and text
- optional image captions

This is enough for:

- image retrieval
- text-to-image search
- visual archive exploration

## Suggested query pipeline

For a user query:

1. run SQLite FTS for exact keyword matches
2. run vector search over text chunks
3. merge and rank results
4. if multimodal is enabled, also query CLIP image vectors
5. return:
   - relevant text chunks
   - source document metadata
   - optional related images

## For your semantic analysis ideas

Once chunks and metadata exist, you can do:

- topic frequency over time
- named entities over time
- clustering by decade
- "interest snapshots" for war years or major events
- compare archive attention before/during/after specific events

The key prerequisite is not image extraction. It is:

- reliable text
- clean dates
- chunked searchable corpus

## Concrete recommendation

Start with this order:

1. create metadata index
2. create chunk pipeline
3. create SQLite FTS search
4. create sentence-transformer embeddings + FAISS
5. test retrieval quality
6. only then add extracted images + CLIP

If you want, the next implementation file I would add is a new script that builds the metadata database from `output/pdfs/` and `output/plain_text/` without changing any existing data.




## What each file would do:

db.py

connect to SQLite
helper to fetch chunks/documents by ids
search_fts.py

search_fts(query, limit=20)
search_vector.py

load model/index
search_vector(query, limit=20)
search.py

search(query, limit=20)
merge FTS + vector results
maybe group by document
app.py

FastAPI app
/search?q=...
Stepwise debugging path:

Step 1:

get search_fts.py working from a Python shell
Step 2:

get search_vector.py working from a Python shell
Step 3:

get search.py returning a nice Python dict
Step 4:

wrap it in FastAPI
Step 5:

hit it from browser or curl
Step 6: