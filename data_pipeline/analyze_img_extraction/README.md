# Image Extraction Gallery

This folder contains a small static gallery for browsing extracted image regions in `output/extracted_images` by decade and year.

The gallery is split into two layers:

1. Python build scripts that scan the extracted images and generate lightweight metadata plus optional thumbnails.
2. A static HTML/CSS/JS viewer that loads one decade at a time and expands full images on click.

## Files

- `build_image_manifest.py`: scans `output/extracted_images` and writes JSON manifests into `gallery/data`.
- `build_thumbnails.py`: generates smaller thumbnails into `gallery/thumbs` so the browser does not load the original full-size crops for every grid item.
- `build_gallery.py`: convenience wrapper that runs manifest generation and, unless skipped, thumbnail generation.
- `gallery/index.html`: static gallery entrypoint.
- `gallery/app.js`: gallery UI logic.
- `gallery/styles.css`: gallery styling.

## Why this is split up

`output/extracted_images` is large enough that a single HTML page pointing directly at the original files would be slow and memory-heavy.

The gallery therefore:

- loads decade summaries first
- fetches one decade JSON file at a time
- renders year sections on demand
- uses thumbnails in the grid
- opens the original image only when clicked

## Build the manifests

From the repository root:

```bash
python3 data_pipeline/analyze_img_extraction/build_image_manifest.py
```

This writes:

- `data_pipeline/analyze_img_extraction/gallery/data/index.json`
- one JSON file per decade such as `1900s.json`, `1930s.json`, etc.

## Build thumbnails

Thumbnail generation requires `Pillow`.

```bash
python3 -m pip install Pillow
python3 data_pipeline/analyze_img_extraction/build_thumbnails.py
```

Useful options:

```bash
python3 data_pipeline/analyze_img_extraction/build_thumbnails.py --start-year 1902 --end-year 1909
python3 data_pipeline/analyze_img_extraction/build_thumbnails.py --start-year 1930 --end-year 1939
python3 data_pipeline/analyze_img_extraction/build_thumbnails.py --limit 500
```

Those filters make it easy to build thumbnails in smaller batches instead of all at once.

## One-command build

```bash
python3 data_pipeline/analyze_img_extraction/build_gallery.py --skip-thumbnails
python3 data_pipeline/analyze_img_extraction/build_gallery.py
```

If `Pillow` is not installed, `--skip-thumbnails` still gives you a usable gallery manifest. The UI will fall back to the original image when a thumbnail is missing, though that is slower.

## Serve the gallery

The gallery uses `fetch()`, so it should be served over HTTP rather than opened directly as a `file://` page.

Serve the repository root:

```bash
python3 -m http.server 8000
```

Then open:

```text
http://127.0.0.1:8000/data_pipeline/analyze_img_extraction/gallery/index.html
```

Serving the repo root matters because the gallery references:

- `data_pipeline/analyze_img_extraction/gallery/data/...`
- `data_pipeline/analyze_img_extraction/gallery/thumbs/...`
- `output/extracted_images/...`

## Manifest shape

`index.json` stores decade summaries, counts, and preview items for the landing page.

Each decade file stores:

- decade label
- total image count
- per-year counts
- per-year preview items
- full item lists for that year

Each image item includes:

- year
- month
- decade
- doc_id
- label
- page number
- region index
- source-relative path
- full image path
- thumbnail path

