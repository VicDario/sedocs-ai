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


def test_id_shaped_number_right_after_a_period_is_found(scan):
    digits = "12" + "345" + "678"
    dotted = f"{digits[:2]}.{digits[2:5]}.{digits[5:]}-5"
    assert scan.scan_text(f"See the annex.{digits}-5 is the holder", [])
    assert scan.scan_text(f"ID.{dotted}", [])
    assert scan.scan_text(f".{digits}-K", [])
    # the tail of a longer dotted number is still not an ID number
    assert scan.scan_text(f"build 1.{dotted} and 3.{digits}-5", []) == []


def _repository(tmp_path, scan, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    monkeypatch.setattr(scan, "TERMS_FILE", tmp_path / ".private" / "forbidden-terms.txt")

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    return git


def test_staged_submodule_pointer_is_skipped_and_the_rest_is_still_scanned(scan, tmp_path, monkeypatch, capsys):
    git = _repository(tmp_path, scan, monkeypatch)
    (tmp_path / "notes.txt").write_text("nothing personal here\n", encoding="utf-8")
    git("add", "notes.txt")
    # a submodule entry in the index is a commit pointer, not a file with content
    git("update-index", "--add", "--cacheinfo", "160000," + "a" * 40 + ",vendor/library")
    assert scan.main() == 0, capsys.readouterr().out
    assert "privacy scan OK" in capsys.readouterr().out

    digits = "12" + "345" + "678"
    (tmp_path / "people.txt").write_text(f"holder {digits}-5\n", encoding="utf-8")
    git("add", "people.txt")
    assert scan.main() == 1
    assert "people.txt:1: text shaped like a national ID number" in capsys.readouterr().out


def test_unreadable_repository_fails_closed_with_a_message(scan, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scan, "ROOT", tmp_path)                 # not a git repository
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert scan.main() == 2
    assert "privacy scan could not read the repository" in capsys.readouterr().out


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


def test_script_outside_the_repository_root_fails_closed(scan, tmp_path, monkeypatch, capsys):
    # a copy of the script inside another repository would otherwise scan nothing and report OK
    _repository(tmp_path, scan, monkeypatch)
    nested = tmp_path / "copied" / "tool"
    nested.mkdir(parents=True)
    digits = "12" + "345" + "678"
    (nested / "people.txt").write_text(f"holder {digits}-5\n", encoding="utf-8")
    monkeypatch.setattr(scan, "ROOT", nested)
    assert scan.main() == 2
    assert "privacy scan could not read the repository" in capsys.readouterr().out


def test_staged_file_whose_name_looks_like_an_index_stage_is_read_itself(scan, tmp_path, monkeypatch, capsys):
    git = _repository(tmp_path, scan, monkeypatch)
    digits = "12" + "345" + "678"
    (tmp_path / "x.txt").write_text("nothing personal here\n", encoding="utf-8")
    (tmp_path / "0:x.txt").write_text(f"holder {digits}-5\n", encoding="utf-8")
    git("add", "x.txt", "0:x.txt")
    assert scan.main() == 1
    assert "0:x.txt:1: text shaped like a national ID number" in capsys.readouterr().out
