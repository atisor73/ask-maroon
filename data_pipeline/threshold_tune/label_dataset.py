"""
label_dataset.py
Tkinter GUI for per-page, per-type count labeling of newspaper PDFs.
For each page I record how many of each content type appear (0 = none).

Requires poppler on PATH: https://github.com/oschwartz10612/poppler-windows/releases

  pip install pdf2image pillow
  python label_dataset.py            # fresh start
  python label_dataset.py --resume   # skip already-labeled pages

Controls:
  + / - buttons (or scroll wheel over a row) -> increment / decrement count
  Enter / Tab -> submit current counts and advance
  Space       -> skip page (not saved)
  Z           -> undo last submission
  Q           -> quit

Output: ~/.ipython/ask-maroon/data_pipeline/threshold_tune/labels.csv
  Columns: archive_path, page_num, year,
           photograph, illustration, map, comic, editorial_cartoon,
           headline, advertisement
  Each value is an integer count (0 if none visible on the page).
"""

import argparse, csv, random, sys
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, messagebox
from PIL import Image, ImageTk
from pdf2image import convert_from_path

PDF_ROOT      = Path.home() / ".ipython/ask-maroon/data_pipeline/threshold_tune/pdfs"
LABELS_CSV    = Path.home() / ".ipython/ask-maroon/data_pipeline/threshold_tune/labels.csv"
PAGES_PER_PDF = 3      # pages sampled per PDF (random, seeded)
DISPLAY_DPI   = 110    # higher = sharper but slower
IMG_MAX_W     = 780
IMG_MAX_H     = 820
SEED          = 42

# Image types: display label, CSV column name, accent colour
CATEGORIES = [
    ("Photograph",        "photograph",        "#2980b9"),
    ("Illustration",      "illustration",      "#8e44ad"),
    ("Map",               "map",               "#16a085"),
    ("Comic / Strip",     "comic",             "#d35400"),
    ("Editorial Cartoon", "editorial_cartoon", "#c0392b"),
    ("Headline / Text",   "headline",          "#7f8c8d"),
    ("Advertisement",     "advertisement",     "#27ae60"),
]
CSV_FIELDS = ["archive_path", "page_num", "year"] + [col for _, col, _ in CATEGORIES]

BG       = "#1a1a2e"
FG       = "#e0e0e0"
PANEL_BG = "#16213e"


def collect_pages(pdf_root: Path) -> list[dict]:
    rng   = random.Random(SEED)
    pages = []
    for year_dir in sorted(pdf_root.iterdir()):
        if not (year_dir.is_dir() and year_dir.name.isdigit()):
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not (month_dir.is_dir() and month_dir.name.isdigit()):
                continue
            for pdf in sorted(month_dir.glob("*.pdf")):
                archive = f"{year_dir.name}/{month_dir.name}/{pdf.name}"
                try:
                    n_pages = len(convert_from_path(str(pdf), dpi=18,
                                                    first_page=1, last_page=1))
                    n_pages = max(n_pages, 1)
                except Exception:
                    n_pages = 1
                for pg in rng.sample(range(n_pages), min(PAGES_PER_PDF, n_pages)):
                    pages.append({
                        "archive_path": archive,
                        "local_path":   str(pdf),
                        "year":         year_dir.name,
                        "page_num":     pg,
                    })
    rng.shuffle(pages)
    return pages


def load_done(labels_csv: Path) -> set[tuple]:
    if not labels_csv.exists():
        return set()
    with open(labels_csv, newline="") as f:
        return {(r["archive_path"], int(r["page_num"])) for r in csv.DictReader(f)}


def ensure_csv(labels_csv: Path):
    if not labels_csv.exists():
        labels_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(labels_csv, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def append_label(labels_csv: Path, row: dict):
    with open(labels_csv, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)


def delete_last_label(labels_csv: Path) -> bool:
    """Remove the last data row. Returns True if successful."""
    if not labels_csv.exists():
        return False
    with open(labels_csv, newline="") as f:
        lines = f.readlines()
    if len(lines) <= 1:   # header only
        return False
    with open(labels_csv, "w", newline="") as f:
        f.writelines(lines[:-1])
    return True


class CounterRow(tk.Frame):
    """A single labelled +/- counter row."""

    def __init__(self, parent, label: str, accent: str, **kw):
        super().__init__(parent, bg=PANEL_BG, **kw)
        self._var = tk.IntVar(value=0)

        lbl_font  = tkfont.Font(family="Segoe UI", size=11)
        num_font  = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        btn_font  = tkfont.Font(family="Segoe UI", size=16, weight="bold")

        tk.Frame(self, bg=accent, width=5).pack(side="left", fill="y", padx=(0, 8))
        tk.Label(self, text=label, bg=PANEL_BG, fg=FG,
                 font=lbl_font, width=18, anchor="w").pack(side="left")
        tk.Button(self, text="-", font=btn_font, bg="#2c2c54", fg="#ff6b6b",
                  relief="flat", bd=0, width=2, cursor="hand2",
                  command=self.decrement).pack(side="left", padx=(8, 2))
        self._lbl = tk.Label(self, textvariable=self._var, bg=PANEL_BG,
                              fg=accent, font=num_font, width=3, anchor="center")
        self._lbl.pack(side="left")
        tk.Button(self, text="+", font=btn_font, bg="#2c2c54", fg="#6bcb77",
                  relief="flat", bd=0, width=2, cursor="hand2",
                  command=self.increment).pack(side="left", padx=(2, 8))

        self.bind_all_children("<MouseWheel>", self._on_wheel)

    def bind_all_children(self, event, handler):
        self.bind(event, handler)
        for child in self.winfo_children():
            child.bind(event, handler)

    def _on_wheel(self, event):
        """Scroll only when pointer is inside this row."""
        wx, wy = self.winfo_rootx(), self.winfo_rooty()
        pw, ph = self.winfo_width(), self.winfo_height()
        ex, ey = event.x_root, event.y_root
        if wx <= ex <= wx + pw and wy <= ey <= wy + ph:
            if event.delta > 0:
                self.increment()
            else:
                self.decrement()

    def increment(self):
        self._var.set(self._var.get() + 1)

    def decrement(self):
        if self._var.get() > 0:
            self._var.set(self._var.get() - 1)

    def get(self) -> int:
        return self._var.get()

    def reset(self):
        self._var.set(0)


class Labeler:

    def __init__(self, pages: list[dict], labels_csv: Path):
        self.pages      = pages
        self.labels_csv = labels_csv
        self.cursor     = 0
        self.labeled    = 0
        self.skipped    = 0
        self._tk_img    = None
        self._history   = []   # for undo: list of cursor positions

        ensure_csv(labels_csv)

        self.root = tk.Tk()
        self.root.title("Newspaper Page Labeler")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        bold  = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        small = tkfont.Font(family="Segoe UI", size=10)

        self.status_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.status_var,
                 bg=BG, fg=FG, font=bold, pady=4).pack(fill="x", padx=10)

        self.prog_canvas = tk.Canvas(self.root, height=5, bg="#333355",
                                     bd=0, highlightthickness=0)
        self.prog_canvas.pack(fill="x", padx=10)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=6)

        self.canvas = tk.Canvas(body, bg="#111122", bd=0, highlightthickness=0,
                                width=IMG_MAX_W, height=IMG_MAX_H)
        self.canvas.pack(side="left", fill="both", expand=True)

        panel = tk.Frame(body, bg=PANEL_BG, width=310)
        panel.pack(side="right", fill="y", padx=(10, 0))
        panel.pack_propagate(False)

        tk.Label(panel, text="Count per type on this page",
                 bg=PANEL_BG, fg="#888899", font=small).pack(pady=(12, 6))

        self.counters: dict[str, CounterRow] = {}
        for display, col, accent in CATEGORIES:
            row = CounterRow(panel, display, accent)
            row.pack(fill="x", padx=10, pady=4, ipady=6)
            self.counters[col] = row

        btn_area = tk.Frame(panel, bg=PANEL_BG)
        btn_area.pack(fill="x", padx=10, pady=(16, 6))

        tk.Button(btn_area, text="Submit  (Enter)",
                  font=tkfont.Font(family="Segoe UI", size=13, weight="bold"),
                  bg="#27ae60", fg="white", relief="flat",
                  command=self.submit, cursor="hand2",
                  padx=10, pady=10).pack(fill="x", pady=(0, 6))

        tk.Button(btn_area, text="Skip  (Space)",
                  font=small, bg="#555577", fg=FG, relief="flat",
                  command=self.skip, cursor="hand2",
                  padx=10, pady=8).pack(fill="x", pady=(0, 4))

        tk.Button(btn_area, text="Undo last  (Z)",
                  font=small, bg="#3d3d5c", fg="#aaaacc", relief="flat",
                  command=self.undo, cursor="hand2",
                  padx=10, pady=8).pack(fill="x")

        tk.Label(panel,
                 text="Scroll wheel over a row to adjust count",
                 bg=PANEL_BG, fg="#555577", font=small,
                 wraplength=270).pack(pady=(10, 0))

        self.root.bind("<Return>", lambda e: self.submit())
        self.root.bind("<space>",  lambda e: self.skip())
        self.root.bind("<z>",      lambda e: self.undo())
        self.root.bind("<Z>",      lambda e: self.undo())
        self.root.bind("<q>",      lambda e: self.quit())
        self.root.bind("<Q>",      lambda e: self.quit())
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self._render()
        self.root.mainloop()

    def submit(self):
        if self.cursor >= len(self.pages):
            return
        p   = self.pages[self.cursor]
        row = {
            "archive_path": p["archive_path"],
            "page_num":     p["page_num"],
            "year":         p["year"],
        }
        for col, counter in self.counters.items():
            row[col] = counter.get()

        append_label(self.labels_csv, row)
        self._history.append(self.cursor)
        self.labeled += 1
        self.cursor  += 1
        self._reset_counters()
        self._render()

    def skip(self):
        self.skipped += 1
        self.cursor  += 1
        self._reset_counters()
        self._render()

    def undo(self):
        if not self._history:
            return
        prev_cursor = self._history.pop()
        if delete_last_label(self.labels_csv):
            self.labeled -= 1
            self.cursor   = prev_cursor
            self._reset_counters()
            self._render()

    def quit(self):
        if messagebox.askokcancel("Quit",
                                   f"Labeled {self.labeled} pages, "
                                   f"skipped {self.skipped}.\nQuit?"):
            self.root.destroy()

    def _reset_counters(self):
        for counter in self.counters.values():
            counter.reset()

    def _render(self):
        total = len(self.pages)
        if self.cursor >= total:
            self.status_var.set(
                f"Done - labeled {self.labeled} pages, skipped {self.skipped}")
            self.canvas.delete("all")
            self.canvas.create_text(
                IMG_MAX_W // 2, IMG_MAX_H // 2,
                text="All pages labeled!\nClose the window.",
                fill=FG, font=("Segoe UI", 18), justify="center")
            return

        p = self.pages[self.cursor]
        self.status_var.set(
            f"[{self.cursor+1}/{total}]  {p['archive_path']}  -  page {p['page_num']+1}"
            f"   |   labeled {self.labeled}   skipped {self.skipped}"
        )

        pct = self.cursor / total
        self.prog_canvas.delete("all")
        w = self.prog_canvas.winfo_width() or IMG_MAX_W
        self.prog_canvas.create_rectangle(0, 0, int(w * pct), 5,
                                           fill="#4488ff", outline="")

        self.canvas.delete("all")
        self.canvas.create_text(IMG_MAX_W // 2, IMG_MAX_H // 2,
                                 text="Loading ...", fill="#666688",
                                 font=("Segoe UI", 14))
        self.root.update_idletasks()
        try:
            imgs = convert_from_path(
                p["local_path"], dpi=DISPLAY_DPI,
                first_page=p["page_num"] + 1,
                last_page=p["page_num"] + 1,
            )
            img: Image.Image = imgs[0]
            img.thumbnail((IMG_MAX_W, IMG_MAX_H), Image.LANCZOS)
            self._tk_img = ImageTk.PhotoImage(img)
            self.canvas.config(width=img.width, height=img.height)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)
        except Exception as exc:
            self.canvas.delete("all")
            self.canvas.create_text(
                IMG_MAX_W // 2, IMG_MAX_H // 2,
                text=f"Error loading page:\n{exc}",
                fill="#ff6666", font=("Segoe UI", 12), justify="center")


def main():
    ap = argparse.ArgumentParser(
        description="Per-page, per-type count labeler for newspaper PDFs.")
    ap.add_argument("--resume", action="store_true",
                    help="Skip pages already present in labels.csv")
    args = ap.parse_args()

    if not PDF_ROOT.exists():
        sys.exit(f"PDF root not found: {PDF_ROOT}\nCheck PDF_ROOT at the top of this script.")

    print("Scanning PDFs ...")
    pages = collect_pages(PDF_ROOT)
    print(f"  {len(pages)} page slots across all PDFs")

    if args.resume:
        done  = load_done(LABELS_CSV)
        pages = [p for p in pages
                 if (p["archive_path"], p["page_num"]) not in done]
        print(f"  Resuming - {len(done)} already labeled, {len(pages)} remaining")

    if not pages:
        print("Nothing to label. Done.")
        return

    print(f"\nStarting labeler ...  Output -> {LABELS_CSV}\n")
    Labeler(pages, LABELS_CSV)
    print(f"\nSession complete.  Labels saved to {LABELS_CSV}")


if __name__ == "__main__":
    main()
