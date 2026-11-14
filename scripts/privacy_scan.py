#!/usr/bin/env python3
"""Privacy scan for the files tracked (or staged) in this repository.

Two checks:
1. No text shaped like a national ID number: digit groups separated by dots, a hyphen and a check digit.
2. No term from the optional local list `.private/forbidden-terms.txt`, which is git-ignored so
   that the terms themselves never enter the repository.

Usage: python scripts/privacy_scan.py            (scans `git ls-files` plus staged files)
Exit code 1 when something is found.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_FILE = ROOT / ".private" / "forbidden-terms.txt"
ID_NUMBER = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".pptx", ".xlsx", ".zip"}


def fold(text: str) -> str:
    """Lower-case and strip accents so that the match ignores both."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower()


def tracked_files() -> list[Path]:
    names: set[str] = set()
    for args in (["git", "ls-files"], ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]):
        out = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout
        names.update(line for line in out.splitlines() if line)
    return sorted(ROOT / name for name in names if (ROOT / name).is_file())


def load_terms() -> list[tuple[str, re.Pattern[str]]]:
    if not TERMS_FILE.is_file():
        return []
    terms = []
    for line in TERMS_FILE.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            terms.append((term, re.compile(r"(?<!\w)" + re.escape(fold(term)) + r"(?!\w)")))
    return terms


def docx_text(path: Path) -> str:
    """Text of the XML parts of an Office file, so binary documents are scanned too."""
    import zipfile

    chunks = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                chunks.append(re.sub(r"<[^>]+>", " ", archive.read(name).decode("utf-8", "replace")))
    return "\n".join(chunks)


def main() -> int:
    terms = load_terms()
    findings: list[str] = []
    for path in tracked_files():
        rel = path.relative_to(ROOT)
        if path.suffix.lower() in {".docx", ".pptx", ".xlsx"}:
            text = docx_text(path)
        elif path.suffix.lower() in BINARY_SUFFIXES:
            continue
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if ID_NUMBER.search(line):
                findings.append(f"{rel}:{number}: text shaped like a national ID number")
            folded = fold(line)
            for term, pattern in terms:
                if pattern.search(folded):
                    findings.append(f"{rel}:{number}: forbidden term ({len(term)} characters, see local list)")
    if findings:
        print("privacy scan FAILED")
        for finding in findings:
            print("  " + finding)
        return 1
    note = f"{len(terms)} local terms" if terms else "no local term list, ID-number check only"
    print(f"privacy scan OK ({note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
