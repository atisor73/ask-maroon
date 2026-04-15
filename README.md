# ask-maroon
<img src="imgs/demo.png" width="100%">

This project enables users to search the Maroon archives dating from 1902-1985. Given a query, ask-maroon seeks to retrieve the most relevant set of articles from the collection.

From a technical standpoint, the archive's .txt files are chunked and semantically embedded using a model specifically tuned for semantic retrieval purposes, in our case we use sentence-transformers and open-ai. These embeddings are stored alongside the original pdfs. At query time, the user’s input is embedded with the same model, and cosine similarity is used to identify semantically relevant matches. In parallel, full-text search (FTS) is performed, and results from both methods are combined and ranked before being returned to the user. During chunking, approximate page numbers are inferred to link results back to their original document locations.

This is all to say, this tool is not perfect, as digitizing the text files from pdfs involves some requisite amount of spelling error and noise. The poor quality of the OCR could be very sensitive to noise and spelling errors. Users are recommended to try extending their queries to include more relevant alternative keywords (i.e, bikes, bike, bicycles, cyclists, etc.).


Additionally, ask-maroon might struggle with queries that involve higher-level reasoning or inference. For example, if one were to query "poems", one would get articles directly using words related to 'poems': 'poetry', 'verse', etc. But the tool would not be able to infer or locate articles where an actual poem exists, that does not explicitly include any word related to poetry (try searching for this and see if the 1979-0928 issue comes up). We are relying entirely on the sentence and document embedding, both of which are black-box tools we did not develop ourselves, to sufficiently infer poetry. At this point we have not integrated an LLM at the end of the pipeline to synthesize the retrieved documents, and the tool's primary use is document retrieval where the query is expected to align with articles in the embedding space. 

We are working to integrate image embeddings and other new features.




# To-do's
- Make .mov demo

- B1. Add info button explaining UI, randomize button, modeling, link to github/issues. FAQ section?
	- highlighting
	- It is really saying:
		“this whole chunk is semantically near the query”
		Then the UI layer says:
		“within this chunk, here is a plausible phrase or sentence that best aligns with the query”
		That means the highlight is an interpretive aid, not a faithful window into the model’s internal scoring.

		So could that be misleading?
		A little, yes, if it’s presented too strongly.
		- also note that animation while search is loading is currently on a fake timer as  otherwise we'd have to stream the backend as it's running
	
- B2. Add better documentation to each individual file as to what it is doing methodologically and how it is doing it (it will force you to do your own code review)




- E. Search for 'typical set': Toggle btw Greedy search vs. Serendipitous search.? or 
  - Query Expansion: LLM (see below in E2 for details):
	- use a local LLM to rewrite a query into:	related entities, alternate phrasings,narrower/broader subqueries
	- free in licensing/runtime terms if you run locally, but not free in compute/time
	- 
  - another methodological shift can be to wrap the query in an LLM that generates a more targeted response
  - for example, if I am looking for russian authors, currently the embedding will literally just embed "russian authors" as a vector instead of doing what a NTP LLM would do (I think?) which is generate other subqueries
  - optionally ask an LLM to generate a few related entity-rich subqueries, run retrieval on all of them, merge results


- Z. figure out production/deployment & make budget proposal 
	- 1. storage for 300 GB PDFs/data (aws s3 or cloudflare r2)
	- 2. backend fastAPI (ec2 or lightsail)
	- 3. frontend hosting/CDN (aws s3+ cloudfront or cloudflare pages)


(frontend calls backend over HTTPS)

	- one option: Use Cloudflare for frontend + storage, and one small server for FastAPI.
		- Frontend: Cloudflare Pages
		- Files: Cloudflare R2
		- Backend: one small VM on AWS Lightsail or EC2

# Finished

add 'advanced search options'  dropdown
and then year range slider lives here
as well as Serendipitous search 

- A. Add year filter? add visual timeline?
  - would be cool if we displayed an interactive timeline and then draw a circle for every search result that shows up (but we are pretty limited by number of results returned by backend)
  - Show distribution of chunk score?


# data_pipeline/

`run.sh` runs files sequentially. However, recommendation is to run scripts one at a time in case of failure and checking for correct outputs.

`scraper_0.py`
- output/links.json: document links 
- output/failed_pages.json: failed pages to retrieve document links (page contains a set of documents)

`scraper_1.py`
- output/pdf-links.json: pdf links within document links

`scraper_2.py`
- output/pdfs/...: pdf of old archives

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