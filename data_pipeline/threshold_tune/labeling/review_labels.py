"""
review_labels.py
Local Tkinter GUI for reviewing model detections from detection_pass.ipynb.

For each page:
  Y       -> all detections correct, move on
  N       -> problem screen: mark each box FP or not, add FN counts per class
  Z       -> undo last submission
  Q       -> quit

Place detections_review.json (downloaded from Colab) next to this script.

  pip install pdf2image pillow
  python review_labels.py
  python review_labels.py --resume

Output: ~/.ipython/ask-maroon/data_pipeline/threshold_tune/labels.csv
  Columns: archive_path, page_num, year,
           photograph, illustration, map, comic, editorial_cartoon,
           is_fp_{class} counts per detection (stored in detections_reviewed.json)
"""

import argparse, csv, json, sys
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, messagebox
from PIL import Image, ImageTk, ImageDraw
from pdf2image import convert_from_path

PDF_ROOT         = Path.home() / ".ipython/ask-maroon/data_pipeline/threshold_tune/pdfs"
DETECTIONS_JSON  = Path(__file__).parent / "detections_review.json"
LABELS_CSV       = Path.home() / ".ipython/ask-maroon/data_pipeline/threshold_tune/labeling/labels.csv"
REVIEWED_JSON    = Path.home() / ".ipython/ask-maroon/data_pipeline/threshold_tune/labeling/detections_reviewed.json"

DISPLAY_DPI  = 110
IMG_MAX_W    = 820
IMG_MAX_H    = 900

# class id -> display name, color for box drawing
CLASS_INFO = {
    0: ("Photograph",        "#2980b9"),
    1: ("Illustration",      "#8e44ad"),
    2: ("Map",               "#16a085"),
    3: ("Comic",             "#d35400"),
    4: ("Editorial Cartoon", "#c0392b"),
    5: ("Headline",          "#7f8c8d"),
    6: ("Advertisement",     "#27ae60"),
}

IMAGE_CLASS_IDS = {0, 1, 2, 3, 4}

CLASS_COL_MAP = {
    0: "photograph",
    1: "illustration",
    2: "map",
    3: "comic",
    4: "editorial_cartoon",
}

CSV_FIELDS = (["archive_path", "page_num", "year"] +
              list(CLASS_COL_MAP.values()))

BG       = "#1a1a2e"
FG       = "#e0e0e0"
PANEL_BG = "#16213e"
GREEN    = "#27ae60"
RED      = "#c0392b"


def load_detections(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def load_done(labels_csv: Path) -> set[tuple]:
    if not labels_csv.exists():
        return set()
    with open(labels_csv, newline="") as f:
        return {(r["archive_path"], int(r["page_num"])) for r in csv.DictReader(f)}


def load_reviewed(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_reviewed(path: Path, reviewed: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(reviewed, f, indent=2)


def ensure_csv(labels_csv: Path):
    if not labels_csv.exists():
        labels_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(labels_csv, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def append_label(labels_csv: Path, row: dict):
    with open(labels_csv, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)


def delete_last_label(labels_csv: Path) -> bool:
    if not labels_csv.exists():
        return False
    with open(labels_csv, newline="") as f:
        lines = f.readlines()
    if len(lines) <= 1:
        return False
    with open(labels_csv, "w", newline="") as f:
        f.writelines(lines[:-1])
    return True


def render_page(det: dict, fp_mask: list[bool] | None = None) -> Image.Image:
    """Render the PDF page and draw detection boxes on it."""
    pdf_path = PDF_ROOT / det["archive_path"]
    imgs = convert_from_path(str(pdf_path), dpi=DISPLAY_DPI,
                             first_page=det["page_num"] + 1,
                             last_page=det["page_num"] + 1)
    img = imgs[0].copy()

    # scale boxes from inference DPI (150) to display DPI
    scale = DISPLAY_DPI / 150.0
    draw = ImageDraw.Draw(img)

    for i, (box, score, cls_id) in enumerate(
            zip(det["boxes"], det["scores"], det["classes"])):
        name, color = CLASS_INFO.get(cls_id, ("Unknown", "#ffffff"))
        x1, y1, x2, y2 = [v * scale for v in box]

        # FPs drawn in red with strikethrough feel (dashed not available in PIL easily,
        # so I draw in red with a different line width)
        if fp_mask and fp_mask[i]:
            draw.rectangle([x1, y1, x2, y2], outline="#ff0000", width=4)
            draw.line([x1, y1, x2, y2], fill="#ff0000", width=2)
        else:
            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

        label = f"{i+1} {name} {score:.2f}"
        draw.rectangle([x1, y1, x1 + len(label) * 6, y1 + 14],
                       fill=color if not (fp_mask and fp_mask[i]) else "#ff0000")
        draw.text((x1 + 2, y1 + 1), label, fill="white")

    img.thumbnail((IMG_MAX_W, IMG_MAX_H), Image.LANCZOS)
    return img


class Reviewer:

    def __init__(self, detections: list[dict], labels_csv: Path, reviewed_json: Path):
        self.detections   = detections
        self.labels_csv   = labels_csv
        self.reviewed_json = reviewed_json
        self.reviewed     = load_reviewed(reviewed_json)
        self.cursor       = 0
        self.accepted     = 0
        self.corrected    = 0
        self._tk_img      = None
        self._history     = []   # list of cursor positions for undo

        ensure_csv(labels_csv)

        self.root = tk.Tk()
        self.root.title("Detection Reviewer")
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

        self.panel = tk.Frame(body, bg=PANEL_BG, width=320)
        self.panel.pack(side="right", fill="y", padx=(10, 0))
        self.panel.pack_propagate(False)

        self.root.bind("<y>", lambda e: self.accept())
        self.root.bind("<Y>", lambda e: self.accept())
        self.root.bind("<n>", lambda e: self.open_correction())
        self.root.bind("<N>", lambda e: self.open_correction())
        self.root.bind("<z>", lambda e: self.undo())
        self.root.bind("<Z>", lambda e: self.undo())
        self.root.bind("<q>", lambda e: self.quit())
        self.root.bind("<Q>", lambda e: self.quit())
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self._build_main_panel()
        self._render()
        self.root.mainloop()

    def _clear_panel(self):
        for w in self.panel.winfo_children():
            w.destroy()

    def _build_main_panel(self):
        self._clear_panel()
        small = tkfont.Font(family="Segoe UI", size=10)
        big   = tkfont.Font(family="Segoe UI", size=13, weight="bold")

        tk.Label(self.panel, text="Are all detections correct?",
                 bg=PANEL_BG, fg="#888899", font=small).pack(pady=(16, 12))

        tk.Button(self.panel, text="Y  Yes, all good",
                  font=big, bg=GREEN, fg="white", relief="flat",
                  command=self.accept, cursor="hand2",
                  padx=10, pady=12).pack(fill="x", padx=10, pady=(0, 8))

        tk.Button(self.panel, text="N  No, problems here",
                  font=big, bg=RED, fg="white", relief="flat",
                  command=self.open_correction, cursor="hand2",
                  padx=10, pady=12).pack(fill="x", padx=10)

        tk.Button(self.panel, text="Undo last  (Z)",
                  font=small, bg="#3d3d5c", fg="#aaaacc", relief="flat",
                  command=self.undo, cursor="hand2",
                  padx=10, pady=8).pack(fill="x", padx=10, pady=(16, 0))

        # show detection list for reference
        det = self.detections[self.cursor]
        if det["boxes"]:
            tk.Label(self.panel, text="Detections on this page:",
                     bg=PANEL_BG, fg="#888899", font=small).pack(pady=(16, 4))
            for i, (score, cls_id) in enumerate(zip(det["scores"], det["classes"])):
                name, color = CLASS_INFO.get(cls_id, ("Unknown", "#ffffff"))
                tk.Label(self.panel,
                         text=f"  {i+1}. {name}  ({score:.2f})",
                         bg=PANEL_BG, fg=color, font=small,
                         anchor="w").pack(fill="x", padx=14)
        else:
            tk.Label(self.panel, text="No detections on this page.",
                     bg=PANEL_BG, fg="#555577", font=small).pack(pady=(16, 4))

    def _build_correction_panel(self):
        """Panel for marking FPs per box and FN counts per class."""
        self._clear_panel()
        small = tkfont.Font(family="Segoe UI", size=10)
        bold  = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        det = self.detections[self.cursor]

        tk.Label(self.panel, text="Mark false positives:",
                 bg=PANEL_BG, fg="#888899", font=bold).pack(pady=(12, 6))

        # FP checkboxes per detection
        self._fp_vars = []
        for i, (score, cls_id) in enumerate(zip(det["scores"], det["classes"])):
            name, color = CLASS_INFO.get(cls_id, ("Unknown", "#ffffff"))
            var = tk.BooleanVar(value=False)
            self._fp_vars.append(var)
            row = tk.Frame(self.panel, bg=PANEL_BG)
            row.pack(fill="x", padx=10, pady=2)
            tk.Checkbutton(row, text=f"{i+1}. {name} ({score:.2f})  = FP",
                           variable=var, bg=PANEL_BG, fg=color,
                           selectcolor="#2c2c54", activebackground=PANEL_BG,
                           font=small).pack(side="left")

        tk.Label(self.panel, text="False negatives (missed detections):",
                 bg=PANEL_BG, fg="#888899", font=bold).pack(pady=(14, 6))

        # FN counters per image class
        self._fn_vars = {}
        for class_id, col in CLASS_COL_MAP.items():
            name, color = CLASS_INFO[class_id]
            var = tk.IntVar(value=0)
            self._fn_vars[col] = var
            row = tk.Frame(self.panel, bg=PANEL_BG)
            row.pack(fill="x", padx=10, pady=2)
            tk.Label(row, text=f"{name}:", bg=PANEL_BG, fg=color,
                     font=small, width=16, anchor="w").pack(side="left")
            tk.Button(row, text="-", bg="#2c2c54", fg="#ff6b6b",
                      relief="flat", width=2,
                      command=lambda v=var: v.set(max(0, v.get() - 1))
                      ).pack(side="left")
            tk.Label(row, textvariable=var, bg=PANEL_BG, fg=color,
                     font=small, width=3).pack(side="left")
            tk.Button(row, text="+", bg="#2c2c54", fg="#6bcb77",
                      relief="flat", width=2,
                      command=lambda v=var: v.set(v.get() + 1)
                      ).pack(side="left")

        tk.Button(self.panel, text="Submit Corrections  (Enter)",
                  font=bold, bg=GREEN, fg="white", relief="flat",
                  command=self.submit_correction, cursor="hand2",
                  padx=10, pady=10).pack(fill="x", padx=10, pady=(14, 4))

        tk.Button(self.panel, text="Cancel  (back to Y/N)",
                  font=small, bg="#555577", fg=FG, relief="flat",
                  command=self._back_to_main, cursor="hand2",
                  padx=10, pady=8).pack(fill="x", padx=10)

        self.root.bind("<Return>", lambda e: self.submit_correction())

    def _back_to_main(self):
        self.root.unbind("<Return>")
        self._build_main_panel()
        # redraw without FP highlights
        self._show_image(self.detections[self.cursor])

    def accept(self):
        if self.cursor >= len(self.detections):
            return
        det = self.detections[self.cursor]

        # all detections are correct TPs; FNs = 0
        record = self._build_record(det, fp_mask=[], fn_counts={})
        self._save_record(det, record)
        self.accepted += 1
        self._advance()

    def open_correction(self):
        self._build_correction_panel()
        # redraw with box numbers visible
        self._show_image(self.detections[self.cursor])

    def submit_correction(self):
        self.root.unbind("<Return>")
        det     = self.detections[self.cursor]
        fp_mask = [v.get() for v in self._fp_vars]
        fn_counts = {col: var.get() for col, var in self._fn_vars.items()}

        # redraw with FP boxes marked red before advancing
        self._show_image(det, fp_mask=fp_mask)
        self.root.update_idletasks()

        record = self._build_record(det, fp_mask=fp_mask, fn_counts=fn_counts)
        self._save_record(det, record)
        self.corrected += 1
        self._advance()

    def _build_record(self, det: dict, fp_mask: list, fn_counts: dict) -> dict:
        """Build the reviewed record with TP counts per class derived from detections."""
        tp_counts = {col: 0 for col in CLASS_COL_MAP.values()}
        for i, (score, cls_id) in enumerate(zip(det["scores"], det["classes"])):
            if cls_id in CLASS_COL_MAP:
                col = CLASS_COL_MAP[cls_id]
                is_fp = fp_mask[i] if i < len(fp_mask) else False
                if not is_fp:
                    tp_counts[col] += 1

        # ground truth = TPs + FNs
        gt_counts = {col: tp_counts[col] + fn_counts.get(col, 0)
                     for col in CLASS_COL_MAP.values()}

        return {
            "archive_path": det["archive_path"],
            "page_num":     det["page_num"],
            "year":         det["year"],
            "fp_mask":      fp_mask,
            "fn_counts":    fn_counts,
            "tp_counts":    tp_counts,
            "gt_counts":    gt_counts,
            "detections":   {
                "scores":  det["scores"],
                "classes": det["classes"],
                "boxes":   det["boxes"],
            }
        }

    def _save_record(self, det: dict, record: dict):
        self.reviewed.append(record)
        save_reviewed(self.reviewed_json, self.reviewed)

        # also write ground truth counts to labels CSV
        csv_row = {
            "archive_path": det["archive_path"],
            "page_num":     det["page_num"],
            "year":         det["year"],
        }
        csv_row.update(record["gt_counts"])
        self._history.append((self.cursor, csv_row))
        append_label(self.labels_csv, csv_row)

    def undo(self):
        if not self._history:
            return
        prev_cursor, _ = self._history.pop()
        if delete_last_label(self.labels_csv):
            if self.reviewed:
                self.reviewed.pop()
                save_reviewed(self.reviewed_json, self.reviewed)
            self.cursor = prev_cursor
            self._build_main_panel()
            self._render()

    def _advance(self):
        self.cursor += 1
        self.root.unbind("<Return>")
        self._build_main_panel()
        self._render()

    def quit(self):
        if messagebox.askokcancel("Quit",
                                   f"Accepted {self.accepted}, corrected {self.corrected}.\nQuit?"):
            self.root.destroy()

    def _show_image(self, det: dict, fp_mask: list | None = None):
        self.canvas.delete("all")
        self.canvas.create_text(IMG_MAX_W // 2, IMG_MAX_H // 2,
                                 text="Loading ...", fill="#666688",
                                 font=("Segoe UI", 14))
        self.root.update_idletasks()
        try:
            img = render_page(det, fp_mask=fp_mask)
            self._tk_img = ImageTk.PhotoImage(img)
            self.canvas.config(width=img.width, height=img.height)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)
        except Exception as exc:
            self.canvas.delete("all")
            self.canvas.create_text(IMG_MAX_W // 2, IMG_MAX_H // 2,
                                     text=f"Error loading page:\n{exc}",
                                     fill="#ff6666", font=("Segoe UI", 12),
                                     justify="center")

    def _render(self):
        total = len(self.detections)
        if self.cursor >= total:
            self.status_var.set(
                f"Done - accepted {self.accepted}, corrected {self.corrected}")
            self.canvas.delete("all")
            self.canvas.create_text(IMG_MAX_W // 2, IMG_MAX_H // 2,
                                     text="All pages reviewed!\nClose the window.",
                                     fill=FG, font=("Segoe UI", 18), justify="center")
            return

        det = self.detections[self.cursor]
        self.status_var.set(
            f"[{self.cursor+1}/{total}]  {det['archive_path']}  -  page {det['page_num']+1}"
            f"   |   accepted {self.accepted}   corrected {self.corrected}"
        )

        pct = self.cursor / total
        self.prog_canvas.delete("all")
        w = self.prog_canvas.winfo_width() or IMG_MAX_W
        self.prog_canvas.create_rectangle(0, 0, int(w * pct), 5,
                                           fill="#4488ff", outline="")

        self._show_image(det)


def main():
    ap = argparse.ArgumentParser(
        description="Review model detections, mark FPs and FNs per page.")
    ap.add_argument("--resume", action="store_true",
                    help="Skip pages already in labels.csv")
    args = ap.parse_args()

    if not DETECTIONS_JSON.exists():
        sys.exit(f"detections_review.json not found at {DETECTIONS_JSON}\n"
                 "Download it from Colab and place it next to this script.")

    if not PDF_ROOT.exists():
        sys.exit(f"PDF root not found: {PDF_ROOT}")

    detections = load_detections(DETECTIONS_JSON)
    print(f"Loaded {len(detections)} pages from detections_review.json")

    if args.resume:
        done = load_done(LABELS_CSV)
        detections = [d for d in detections
                      if (d["archive_path"], d["page_num"]) not in done]
        print(f"  Resuming - {len(done)} already reviewed, {len(detections)} remaining")

    if not detections:
        print("Nothing to review. Done.")
        return

    print(f"Starting reviewer ...  Output -> {LABELS_CSV}\n")
    Reviewer(detections, LABELS_CSV, REVIEWED_JSON)
    print(f"\nSession complete.  Labels -> {LABELS_CSV}")
    print(f"Full review records -> {REVIEWED_JSON}")


if __name__ == "__main__":
    main()
