# Cloudflare Pages Setup

This frontend is a static site, so Cloudflare Pages can serve it directly from the `frontend/` build output.

## Recommended setup

In Cloudflare Pages, create a new project from this repository with:

- Framework preset: `None`
- Production branch: your main deploy branch
- Build command: `exit 0`
- Build output directory: `frontend`
- Root directory: leave blank

This repository now includes a Pages Function at `functions/api/[[path]].js`, so the frontend can call `/api/*` on the same origin and Cloudflare will forward those requests to your backend.

## Required environment variable

In your Pages project settings, add:

- `API_ORIGIN` = your deployed backend origin, for example `https://your-backend.example.com`

Do not include `/api` at the end unless your backend is actually mounted there.

## How requests work

- Local development keeps using `http://127.0.0.1:8000`
- Cloudflare Pages production and preview deployments use `/api/...`
- The Pages Function proxies `/api/...` to `API_ORIGIN`

That means the frontend does not need browser CORS access to your backend, because requests stay same-origin from the browser's perspective.

## Local workflow

Run the backend:

```bash
uvicorn backend.app:app --reload
```

Serve the frontend:

```bash
python3 -m http.server 3000
```

Then open:

```text
http://127.0.0.1:3000/frontend/
```

## Notes

- The phoenix image is now bundled inside `frontend/` so Pages can deploy the UI without depending on files outside the build output directory.
- If you want to deploy the backend on Cloudflare too, we can do that next, but it is separate from the Pages frontend setup.
