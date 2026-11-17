#!/usr/bin/env python3
"""Privacy scan for the content this repository is about to publish.

Two checks:
1. No text shaped like a national ID number: digit groups, a hyphen and a check digit.
2. No term from the optional local list `.private/forbidden-terms.txt`, which is git-ignored so
   that the terms themselves never enter the repository.

What is scanned: every tracked file, and for files with staged changes the staged content itself
(what the commit will contain), not the copy in the working tree.

Usage: python scripts/privacy_scan.py
Exit code 1 when something is found, 2 when the repository cannot be read. Both block a commit.
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_FILE = ROOT / ".private" / "forbidden-terms.txt"
# Seven or eight digits, with or without dots between the groups, a hyphen and a check digit.
# A period right before it is allowed (end of a sentence); a digit and a period is not, because
# that is the tail of a longer dotted number.
ID_NUMBER = re.compile(r"(?<!\w)(?<!\d\.)(?:\d{1,2}\.\d{3}\.\d{3}|\d{7,8})-[\dkK](?!\w)")
SUBMODULE_MODE = "160000"
OFFICE_SUFFIXES = {".docx", ".pptx", ".xlsx"}
SKIPPED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip"}
TEXT_RUN = re.compile(r"<(?:w|a):t(?:\s[^>]*)?>([^<]*)</(?:w|a):t>")


def fold(text: str) -> str:
    """Lower-case and strip accents so that the match ignores both."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower()


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def _names(*args: str) -> list[str]:
    # -z: names are separated by NUL and never quoted, so non-ASCII file names are not skipped.
    return [name for name in _git(*args, "-z").decode("utf-8", "surrogateescape").split("\0") if name]


def _check_root() -> None:
    """Git answers for whatever repository surrounds ROOT. If that is not the repository this
    script belongs to, its file list says nothing about the files next to the script."""
    top = Path(_git("rev-parse", "--show-toplevel").decode("utf-8", "surrogateescape").strip())
    if top.resolve() != ROOT.resolve():
        raise OSError("this script is not in the scripts folder at the root of the repository git found")


def _submodules() -> set[str]:
    """Paths the index holds as a submodule: a pointer to a commit, with no content to scan."""
    paths = set()
    for entry in _names("ls-files", "--stage"):
        details, _, name = entry.partition("\t")
        if details.split(" ", 1)[0] == SUBMODULE_MODE:
            paths.add(name)
    return paths


def contents() -> list[tuple[str, bytes]]:
    """(path, bytes) of everything to scan; staged files are read from the index."""
    staged = set(_names("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
    submodules = _submodules()
    found = []
    for name in sorted(set(_names("ls-files")) | staged):
        if name in submodules:
            continue
        if name in staged:
            # stage 0 is named, so a file name that starts like a stage number is not misread
            found.append((name, _git("show", f":0:{name}")))
        elif (ROOT / name).is_file():
            found.append((name, (ROOT / name).read_bytes()))
    return found


def load_terms() -> list[tuple[str, re.Pattern[str]]]:
    if not TERMS_FILE.is_file():
        return []
    terms = []
    for line in TERMS_FILE.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            terms.append((term, re.compile(r"(?<!\w)" + re.escape(fold(term)) + r"(?!\w)")))
    return terms


def office_text(data: bytes) -> str:
    """Text of an Office file. Word splits a word across several runs, so the runs of each
    paragraph are joined without separators; the tag-stripped XML is added for everything else."""
    lines = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if not name.endswith((".xml", ".rels")):
                continue
            xml = archive.read(name).decode("utf-8", "replace")
            for paragraph in re.split(r"</(?:w|a):p>", xml):
                joined = "".join(TEXT_RUN.findall(paragraph))
                if joined:
                    lines.append(joined)
            lines.append(re.sub(r"<[^>]+>", " ", xml))
    return "\n".join(lines)


def scan_text(text: str, terms: list[tuple[str, re.Pattern[str]]]) -> list[tuple[int, str]]:
    """(line number, what was found) for one file's text."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if ID_NUMBER.search(line):
            found.append((number, "text shaped like a national ID number"))
        folded = fold(line)
        for term, pattern in terms:
            if pattern.search(folded):
                found.append((number, f"forbidden term ({len(term)} characters, see local list)"))
    return found


def main() -> int:
    terms = load_terms()
    findings: list[str] = []
    try:
        _check_root()
        files = contents()
    except (subprocess.CalledProcessError, OSError) as error:
        reason = (getattr(error, "stderr", None) or b"").decode("utf-8", "replace").strip().splitlines()
        print("privacy scan could not read the repository, so nothing was checked")
        print("  " + (reason[0] if reason else str(error)))
        return 2
    for name, data in files:
        suffix = Path(name).suffix.lower()
        if suffix in SKIPPED_SUFFIXES:
            continue
        try:
            text = office_text(data) if suffix in OFFICE_SUFFIXES else data.decode("utf-8", errors="replace")
        except zipfile.BadZipFile:
            findings.append(f"{name}: cannot be opened as an Office file, so it cannot be scanned")
            continue
        findings += [f"{name}:{number}: {what}" for number, what in scan_text(text, terms)]
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
