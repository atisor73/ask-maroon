"""
Aggregate cleaned text volume by year.

This script scans `output/plain_text_cleaned/`, skips notebook checkpoint
artifacts, and writes yearly summary statistics to
`output/annual_character_counts.csv`.
"""

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
TEXT_ROOT = ROOT / "output" / "plain_text_cleaned"
OUTPUT_CSV = ROOT / "output" / "annual_character_counts.csv"


def iter_text_files(root: Path):
    for path in sorted(root.rglob("*.txt")):
        if ".ipynb_checkpoints" in path.parts:
            continue
        if path.name.endswith("-checkpoint.txt"):
            continue
        yield path


def build_annual_character_counts(text_root: Path = TEXT_ROOT) -> pd.DataFrame:
    rows = []
    for path in iter_text_files(text_root):
        year = int(path.parts[-3])
        text = path.read_text(encoding="utf-8", errors="ignore")
        rows.append(
            {
                "year": year,
                "doc_id": path.stem,
                "character_count": len(text),
            }
        )

    df = pd.DataFrame(rows)
    annual = (
        df.groupby("year", as_index=False)
        .agg(
            document_count=("doc_id", "count"),
            total_character_count=("character_count", "sum"),
            average_character_count=("character_count", "mean"),
        )
        .sort_values("year")
    )
    annual["average_character_count"] = annual["average_character_count"].round(2)
    return annual


def main() -> None:
    annual = build_annual_character_counts()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    annual.to_csv(OUTPUT_CSV, index=False)
    print(f"Wrote {OUTPUT_CSV}")
    print(annual.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
