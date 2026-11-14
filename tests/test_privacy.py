"""The repository must never carry personal data: this runs the same scan as the commit hook."""
import importlib.util
import io
import re
import subprocess
from pathlib import Path

import docx
import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def scan():
    spec = importlib.util.spec_from_file_location("privacy_scan", ROOT / "scripts" / "privacy_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True).returncode != 0,
                    reason="not a git checkout")
def test_tracked_files_pass_the_privacy_scan(scan, capsys):
    assert scan.main() == 0, capsys.readouterr().out


def test_id_shaped_numbers_are_found_with_and_without_dots(scan):
    digits = "12" + "345" + "678"                       # assembled here so this file passes the scan itself
    dotted = f"{digits[:2]}.{digits[2:5]}.{digits[5:]}-5"
    assert [what for _, what in scan.scan_text(f"ID {dotted} on file", [])] == ["text shaped like a national ID number"]
    assert scan.scan_text(f"ID {digits}-K on file", [])
    assert scan.scan_text("pages 135-137, version 2.5.1, phone 555-0100", []) == []


def test_terms_match_whole_words_ignoring_case_and_accents(scan):
    terms = [("Example Name", re.compile(r"(?<!\w)" + re.escape(scan.fold("Éxample Name")) + r"(?!\w)"))]
    assert scan.scan_text("signed by EXAMPLE NAME yesterday", terms)
    assert scan.scan_text("signed by Example Names", terms) == []


def test_office_text_joins_the_runs_word_splits(scan):
    document = docx.Document()
    paragraph = document.add_paragraph()
    for piece in ("Confi", "den", "tial"):
        paragraph.add_run(piece)
    buffer = io.BytesIO()
    document.save(buffer)
    assert "Confidential" in scan.office_text(buffer.getvalue())
