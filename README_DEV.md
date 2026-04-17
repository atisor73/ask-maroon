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

