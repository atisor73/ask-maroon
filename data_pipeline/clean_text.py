"""
Prepare cleaned document text from raw archive extractions.

Given the raw plain-text output of PDF/OCR extraction, this script fixes common
character- and spacing-level errors, conservatively splits likely glued words,
and produces cleaner text files for chunking, embedding, and full-text search.

Note: The tokenizing you see here is not in the model-token sense, but instead
a regex-based text splitting so clean word-like pieces can be selectively split.
The key line is: parts = TOKEN_RE.findall(normalized).
This breaks the text into alternating chunks: word-like alphabetic tokens,
everything else, like punctuation, spaces, newlines, numbers, symbols.
Ex: for "Hutchins,saidTheStudents", it can inspect the alphabetic parts and decide
whether a word looks suspicious.

clean_word() then uses wordsegment.segment(...) on the lowercase token.
This is a word segmentation tool that splits glued text like 'inthe' -> 'in the'
The code is conservative: it only accepts the split if should_segment(...) thinks 
it looks plausible otherwise it keeps the original token.
"""


import re
from pathlib import Path

from tqdm import tqdm
from wordsegment import load, segment


ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "output" / "plain_text"
OUTPUT_DIR = ROOT / "output" / "plain_text_cleaned"

TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|[^A-Za-z]+")
JOINED_LINEBREAK_RE = re.compile(r"(\w)[¬-]\s+(\w)")
LOWER_TO_UPPER_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
LETTER_TO_DIGIT_RE = re.compile(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])")
REPLACEMENT_RE = re.compile(r"[�\ufffd]")
BROKEN_APOSTROPHE_RE = re.compile(r"(?<=\w)[‘’`](?=\w)")
PUNCT_TO_WORD_RE = re.compile(r"(?<=[,.;:!?])(?=[A-Za-z])")
WORD_TO_OPEN_PAREN_RE = re.compile(r"(?<=[A-Za-z])(?=[\(\[])")
NOISE_RE = re.compile(r"[^\S\n]+")
COMMON_SMALL_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "with",
}


# Normalize raw OCR/extracted text by fixing line breaks, broken characters, ligatures, and missing spaces.
def normalize_raw_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Fix OCR line-break hyphenation like "Hutch¬\nins" or "Hutch-\nins".
    text = JOINED_LINEBREAK_RE.sub(r"\1\2", text)
    text = REPLACEMENT_RE.sub("", text)
    text = text.replace("¬", "")
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = text.replace("\u00a0", " ")
    text = BROKEN_APOSTROPHE_RE.sub("", text)
    # Recover some missing spaces introduced by extraction.
    text = LOWER_TO_UPPER_RE.sub(" ", text)
    text = LETTER_TO_DIGIT_RE.sub(" ", text)
    text = PUNCT_TO_WORD_RE.sub(" ", text)
    text = WORD_TO_OPEN_PAREN_RE.sub(" ", text)
    return text

# Decide whether a token looks like a glued OCR word that should be split into multiple words.
def should_segment(token: str, pieces: list[str]) -> bool:
    if token != token.lower():
        return False
    if len(token) < 6:
        return False
    if len(pieces) <= 1:
        return False
    if len(pieces) > 4:
        return False
    if sum(len(piece) == 1 for piece in pieces) > 1:
        return False
    if "".join(pieces) != token:
        return False

    has_small_word = any(piece in COMMON_SMALL_WORDS for piece in pieces[:-1])
    has_substantial_tail = any(len(piece) >= 4 for piece in pieces[1:])
    looks_like_two_words = all(len(piece) >= 3 for piece in pieces) and any(
        len(piece) >= 5 for piece in pieces
    )
    return (has_small_word and has_substantial_tail) or looks_like_two_words

# Reapply the original token’s capitalization style after splitting it into multiple words.
def preserve_case(token: str, pieces: list[str]) -> str:
    if token.isupper():
        return " ".join(piece.upper() for piece in pieces)
    if token.istitle():
        return " ".join(piece.title() for piece in pieces)
    return " ".join(pieces)

# Clean a single word token by conservatively splitting likely OCR-glued words when appropriate.
def clean_word(token: str) -> str:
    lowered = token.lower()

    # Wordsegment is useful for glued OCR words, but we keep the heuristic conservative.
    pieces = segment(lowered)
    if not should_segment(lowered, pieces):
        return token
        

    return preserve_case(token, pieces)

# Clean a full text document by normalizing OCR artifacts, processing word tokens, and tidying whitespace.
def clean_text(text: str) -> str:
    normalized = normalize_raw_text(text)
    parts = TOKEN_RE.findall(normalized)
    cleaned_parts = []

    for part in parts:
        if part and part[0].isalpha():
            cleaned_parts.append(clean_word(part))
        else:
            cleaned_parts.append(part)

    cleaned = "".join(cleaned_parts)
    cleaned = NOISE_RE.sub(" ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"

# Read one raw plain-text file, clean its contents, and write the cleaned version to the mirrored output path.
def process_file(input_path: Path) -> None:
    relative = input_path.relative_to(INPUT_DIR)
    output_path = OUTPUT_DIR / relative
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw = input_path.read_text(encoding="utf-8", errors="ignore")
    cleaned = clean_text(raw)
    output_path.write_text(cleaned, encoding="utf-8")


# Orchestrate text cleaning for the full corpus by processing every plain-text file into the cleaned-text directory.
def main() -> None:
    load()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(INPUT_DIR.rglob("*.txt"))
    count = 0

    for path in tqdm(files, desc="Cleaning text files"):
        if ".ipynb_checkpoints" in path.parts:
            continue
        process_file(path)
        count += 1

    print(f"Cleaned {count} text files into {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
