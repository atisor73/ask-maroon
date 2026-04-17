
# To-do's
- E. Search for 'typical set':
  - Currently have toggle btw Greedy search vs. Serendipitous search.? or 
  - Query Expansion: LLM (see below in E2 for details):
    - another methodological shift can be to wrap the query in an LLM that generates a more entity-rich query, run retrieval on them, and merge the results
  - use a local LLM to rewrite a query into:	related entities, alternate phrasings,narrower/broader subqueries
    - for example, if I am looking for russian authors, currently the embedding will literally just embed "russian authors" as a vector instead of doing what a NTP LLM would do (I think?) which is generate other subqueries

- [in progress] B2. Add better documentation to each individual file as to what it is doing methodologically and how it is doing it (it will force you to do your own code review)


# Semantic analysis ideas
- PCA -> 3D -> normalize -> sphere -> plot w d3 
- color by year, topic, keyword presence
- spheres preserve angle
- animate spherical embeddings over time


# Data architecture moving from repo -> deployment
what stays on local disk
what moves to R2/S3
what gets preloaded into memory
what costs are per-query vs per-startup vs per-PDF-view.


(frontend calls backend over HTTPS)

	- one option: Use Cloudflare for frontend + storage, and one small server for FastAPI.
		- Frontend: Cloudflare Pages
		- Files: Cloudflare R2
		- Backend: one small VM on AWS Lightsail or EC2


What moves to R2/S3
	Best candidates for object storage:
	raw PDFs
	cleaned/plain text artifacts if you want backup/archive durability
	embedding artifacts as durable blobs:
	text_faiss.index
	text_metadata.jsonl
	text_embeddings.npy
	image derivatives if you add them later
	If choosing between the two, R2 is especially attractive for PDFs because user access/download traffic is much less scary without egress fees.

What gets preloaded into memory
	On backend startup:
	FAISS index
	chunk metadata for vector retrieval
	sentence-transformers model, if using local embeddings at query time
	This already roughly matches your current backend pattern in backend/search_vector.py, where resources are cached in _RESOURCE_CACHE.

	The important production idea is:

	download/load once per worker
	reuse many times
	never re-fetch FAISS from cloud storage per query

------
A practical deployment shape
App server
	FastAPI backend
	serves /search, /search-metadata, document metadata endpoints
	maybe proxies /pdf/{doc_id}, though direct object-storage delivery is often better

Object storage
	store PDFs in R2 or S3
	optionally store large retrieval artifacts too
Search artifacts
	backend downloads FAISS + metadata at startup
	keeps them in memory/local temp disk
	all search requests use local memory afterward
Suggested split
	If you want a pragmatic plan:
	R2/S3
		PDFs
		maybe raw/cleaned text backups
		maybe FAISS artifact backups
	
	Backend local disk / attached volume

		active FAISS index copy
		SQLite DBs
		current working artifacts
	
	Memory
		loaded FAISS index
		loaded metadata structures
		loaded sentence-transformers model


