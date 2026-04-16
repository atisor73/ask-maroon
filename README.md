# ask-maroon
<img src="imgs/demo.png" width="100%">

This project enables users to search the Maroon archives dating from 1902-1985. Given a query, ask-maroon uses semantic embeddings to retrieve what it thinks to be the most relevant set of articles from the collection.

# Limitations
This tool is not perfect, as digitizing the text files from pdfs involves some requisite amount of spelling error and noise. The poor quality of the OCR could be very sensitive to noise and spelling errors. Users are recommended to try extending their queries to include more relevant alternative keywords (i.e, bikes, bike, bicycles, cyclists, etc.).

While semantic embedding can be really rich given how much information can be stored in these higher dimensional spaces, we encourage users to thoughtfully query and parse through the results, and iteratively improve their queries. (One extension we are working on is 'query expansion' using ntp, which is something users can already do by refining their queries with an LLM).

I think Dylan Freedman, author of Semantra, describes this best. 
> Using a semantic search engine is fundamentally different than an exact text matching algorithm.
> For starters, there will always be search results for a given query, no matter how irrelevant it is. 
> The scores may be really low, but the results will never disappear entirely. 
> This is because semantic searching with query arithmetic often reveals useful results amid very minor score differences. 

> Another difference is that Semantra will not necessarily find exact text matches if you query something that directly appears in the document. 
> At a high level, this is because words can mean different things in different contexts, e.g. the word "leaves" can refer to the leaves on trees or to someone leaving. 
> The embedding models that Semantra uses convert all the text and queries you enter into long sequences of numbers that can be mathematically compared, and an exact substring match is not always significant in this sense. See the embeddings concept doc for more information on embeddings.


Additionally, ask-maroon might struggle with queries that involve higher-level reasoning or inference. For example, if one were to query "poems", one would get articles directly using words related to 'poems': 'poetry', 'verse', etc. But the tool would not be able to infer or locate articles where an actual poem exists, that does not explicitly include any word related to poetry (try searching for this and see if the 1979-0928 issue comes up). We are relying entirely on the sentence and document embedding, both of which are black-box tools we did not develop ourselves, to sufficiently infer poetry. At this point we have not integrated an LLM at the end of the pipeline to synthesize the retrieved documents, and the tool's primary use is document retrieval where the query is expected to align with articles in the embedding space. 

We are working to integrate image embeddings and other new features.

# Technical details
The archival text files are chunked and semantically embedded using a model specifically tuned for semantic retrieval purposes. In our case, we use sentence-transformers/all-MiniLM-L6-v2 and OpenAI's text-embedding-3-small that have been trained on pairwise sentence similarity. These embeddings are stored alongside the original pdfs. At query time, the user’s input query is embedded with the same model, and cosine similarity is used to identify semantically relevant matches between the input query and archival texts. In parallel, full-text search (FTS) is performed, and results from both methods are combined and ranked before being returned to the user. During chunking, approximate page numbers are inferred to link results back to their original document locations.

# Model details
A little more about the models:
- `sentence-transformers/all-MiniLM-L6-v2`: "This is a sentence-transformers model: It maps sentences & paragraphs to a 384 dimensional dense vector space and can be used for tasks like clustering or semantic search." Fine-tuned on a dataset of over 1 billion sentence pairs. Training data includes Reddit comment pairs, S2ORC citation/title/abstract pairs, WikiAnswers duplicate questions, PAQ Q/A pairs, and Stack Exchange title/body pairs. The stated fine-tuning objective is contrastive: compute cosine similarities between all sentence pairs in a batch, then apply cross-entropy against the true pair.   
Source: ![Hugging Face model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)   
Note: Both hidden dimension (internal width of transformer layers) and embedding dimension are 384.

- OpenAI's `text-embedding-3-small`: "Embeddings are a numerical representation of text that can be used to measure the relatedness between two pieces of text. Embeddings are useful for search, clustering, recommendations, anomaly detection, and classification tasks." The exact training data and exact loss are not publicly documented.  
Source: ![Docs](https://developers.openai.com/api/docs/models/text-embedding-3-small)  
Note: Hidden dimension is unknown/proprietary, but the embedding dimension is 1,536.

# Tips
Adding double string quotes for keywords (compare query: russian authors vs query: russian authors "tolstoy")
- under the hood this adds an FTS boosting score from 10% -> 40% of the weight
Expand PDF for better command F search experience


# To-do's
- Make .mov demo: "music and jazz around the midway"

- A. Add baseline stats to README/info: get year range, total number of documents, number of documents per year (make histogram), 
  
- E. Search for 'typical set':
  - Currently have toggle btw Greedy search vs. Serendipitous search.? or 
  - Query Expansion: LLM (see below in E2 for details):
    - another methodological shift can be to wrap the query in an LLM that generates a more entity-rich query, run retrieval on them, and merge the results
  - use a local LLM to rewrite a query into:	related entities, alternate phrasings,narrower/broader subqueries
    - for example, if I am looking for russian authors, currently the embedding will literally just embed "russian authors" as a vector instead of doing what a NTP LLM would do (I think?) which is generate other subqueries

- [in progress] B2. Add better documentation to each individual file as to what it is doing methodologically and how it is doing it (it will force you to do your own code review)


- [in progress] Z. Figure out production/deployment & make budget proposal 
  - Cloudflare R2 (Storage), Cloudflare Pages (Front-end), Hetzner or Digital Ocean (Back-end) 
	- 1. storage for 300 GB PDFs/data (aws s3 or cloudflare r2)
	- 2. backend fastAPI (ec2 or lightsail)
	- 3. frontend hosting/CDN (aws s3+ cloudfront or cloudflare pages)


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


# Data_pipeline/
Scrapes maroon archive, generates metadata index for SQLite FTS, performs sentence-level embeddings.

# Backend/
Testing query:
- test_backend.ipynb contains code that runs a query, calling search_fts.py and search_vector.py functions


Testing API:
```
uvicorn backend.app:app --reload
http://127.0.0.1:8000/health
http://127.0.0.1:8000/search?q=student%20protests&backend=openai
http://127.0.0.1:8000/search?q=student%20protests&backend=sentence-transformers
```


# Frontend/
Start backend: `uvicorn backend.app:app --reload`  

Serve frontend: `python3 -m http.server 3000`

Navigate: http://127.0.0.1:3000/frontend/
Backend docs: http://127.0.0.1:8000/docs




# Test queries
crimes related to bikes cycling cyclists bicycles
articles related to haircuts, hairstyles, hair
yarn, quilts, knitting, sewing
yarns


# Authorship
Co-written with GPT-5.4

# Acknowledgements