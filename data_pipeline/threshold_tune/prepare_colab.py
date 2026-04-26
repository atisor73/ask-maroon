"""
prepare_colab.py
Run this on Windows before uploading to Colab.

  python prepare_colab.py

Outputs to ~/.ipython/ask-maroon/data_pipeline/threshold_tune/colab_upload/
  - manifest.csv       year, filename, archive_path, size_bytes
  - pdfs_chunk_01.zip  split into <=4 GB slices for Drive upload limits

Then drag the colab_upload/ folder into Google Drive.
"""

import csv, zipfile, sys
from pathlib import Path

PDF_ROOT  = Path.home() / ".ipython/ask-maroon/data_pipeline/threshold_tune/pdfs"
OUT_DIR   = Path.home() / ".ipython/ask-maroon/data_pipeline/threshold_tune/colab_upload"
CHUNK_GB  = 4   # max size per zip chunk


def collect_pdfs(pdf_root: Path) -> list[dict]:
    pdfs = []
    for year_dir in sorted(pdf_root.iterdir()):
        if not (year_dir.is_dir() and year_dir.name.isdigit()):
            continue
        for pdf in sorted(year_dir.glob("*.pdf")):
            pdfs.append({
                "year":         year_dir.name,
                "filename":     pdf.name,
                "local_path":   str(pdf),
                "archive_path": f"{year_dir.name}/{pdf.name}",
                "size_bytes":   pdf.stat().st_size,
            })
    return pdfs


def write_manifest(pdfs: list[dict], out_dir: Path) -> Path:
    path = out_dir / "manifest.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["year", "filename", "archive_path", "size_bytes"])
        w.writeheader()
        for p in pdfs:
            w.writerow({k: p[k] for k in ["year", "filename", "archive_path", "size_bytes"]})
    return path


def write_chunks(pdfs: list[dict], out_dir: Path, chunk_gb: float) -> int:
    chunk_bytes = int(chunk_gb * 1024 ** 3)
    chunk_idx, used = 1, 0

    def new_zip(idx: int) -> zipfile.ZipFile:
        return zipfile.ZipFile(out_dir / f"pdfs_chunk_{idx:02d}.zip", "w", zipfile.ZIP_DEFLATED)

    zf = new_zip(chunk_idx)
    for p in pdfs:
        fsize = p["size_bytes"]
        if used + fsize > chunk_bytes and used > 0:
            zf.close()
            chunk_idx += 1
            zf = new_zip(chunk_idx)
            used = 0
        zf.write(p["local_path"], p["archive_path"])
        used += fsize
        print(f"  + {p['archive_path']}  ({fsize / 1024**2:.1f} MB)")
    zf.close()
    return chunk_idx


def main():
    if not PDF_ROOT.exists():
        sys.exit(f"PDF root not found: {PDF_ROOT}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Collecting PDFs ...")
    pdfs = collect_pdfs(PDF_ROOT)
    if not pdfs:
        sys.exit("No PDFs found - check PDF_ROOT path.")

    total_gb = sum(p["size_bytes"] for p in pdfs) / 1024 ** 3
    print(f"Found {len(pdfs)} PDFs  ({total_gb:.1f} GB total)\n")

    manifest_path = write_manifest(pdfs, OUT_DIR)
    print(f"Manifest -> {manifest_path}\n")

    print("Writing zip chunks ...")
    n_chunks = write_chunks(pdfs, OUT_DIR, CHUNK_GB)

    print(f"\n{n_chunks} chunk(s) written to:\n   {OUT_DIR}")
    print("\nNext steps:")
    print("  1. Upload the entire colab_upload/ folder to Google Drive.")
    print("  2. In Colab, mount Drive then run:")
    print()
    print("     import zipfile, pathlib")
    print("     DRIVE = pathlib.Path('/content/drive/MyDrive/ask-maroon/threshold_tune')")
    print("     PDF_DIR = DRIVE / 'pdfs'")
    print("     PDF_DIR.mkdir(exist_ok=True)")
    print("     for z in sorted((DRIVE / 'colab_upload').glob('pdfs_chunk_*.zip')):")
    print("         print(f'Extracting {z.name} ...')")
    print("         with zipfile.ZipFile(z) as zf:")
    print("             zf.extractall(PDF_DIR)")


if __name__ == "__main__":
    main()
