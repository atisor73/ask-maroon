#### NEVER MERGE THE BRANCHES main OR dev-frontend OR dev-backend WITH EACH OTHER. They all serve extremely different purposes. 
- The branch `main` is referenced for a stable local deploy, and for the latest up-to-date `README` docs. The code here shows the simplicity of the app without the complexities of getting different servers to communicate with one another.
- The branch `dev-frontend` is used for Cloudflare Pages deployment, and details which branch should be . 
- The branch `dev-backend` is used to run the data_pipeline/ code that pushes raw pdfs and files to the Cloudflare R2 bucket, and then is used to set up a backend FastAPI service on a Hetzner server.
- Both `dev-frontend` and `dev-backend` are compatible with each other, that is, deploying `dev-frontend` on Cloudflare Pages and `dev-backend` on the Hetzner server (or really any VPS) should work. This means that the endpoint of the requests sent from the frontend match the listening ports for the requests on the backend, and that the backend is pointing to the correct R2 bucket of raw pdfs to send back to the frontend. 

In theory it might make sense to merge dev-frontend and dev-backend to a single stable deployment branch. But this state of things reflects the different code used by different services, and allows rigorous testing without risking breaking the frontend/backend. This separation is especially useful when using a tool like codex that has auth to make changes to files. 

If you do want specific changes to copy from one branch to the other, use the following:
```
git checkout branch1
git checkout branch2 -- /path/to/file
```
This will copy the file on branch2 to branch 1. 


**The rest of the docs will likely be migrated to Google Docs**


The code below shows some examples of what running this locally would look like.
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
Start backend: `uvicorn backend.app:app --reload`  

# Frontend/

Serve frontend: `python3 -m http.server 3000`

Navigate: http://127.0.0.1:3000/frontend/
Backend docs: http://127.0.0.1:8000/docs

