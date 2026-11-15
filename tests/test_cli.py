import shutil
from pathlib import Path

import pytest

from sedocs_ai.cli import main

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "harbor-clinic"
HAS_CONVERTER = any(shutil.which(tool) for tool in ("rsvg-convert", "inkscape", "magick"))
HAS_OFFICE = bool(shutil.which("soffice") or shutil.which("libreoffice")) and bool(shutil.which("pdftoppm"))


def test_check_reports_and_sets_the_exit_code(tmp_path, capsys):
    assert main(["check", str(EXAMPLE / "project.yaml")]) == 0
    assert "8 use cases, 6 functional and 3 non-functional requirements; 0 errors, 0 warnings" in capsys.readouterr().out
    broken = tmp_path / "project.yaml"
    broken.write_text((EXAMPLE / "project.yaml").read_text(encoding="utf-8").replace("actors: [veterinarian]", "actors: [nobody]"),
                      encoding="utf-8")
    assert main(["check", str(broken)]) == 1
    assert "unknown-actor" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "missing.yaml")]) == 1
    assert "project model not found" in capsys.readouterr().err


def test_strict_check_fails_on_warnings(tmp_path):
    model = tmp_path / "project.yaml"
    model.write_text((EXAMPLE / "project.yaml").read_text(encoding="utf-8").replace("requirements: [FR-06]", "requirements: []"),
                     encoding="utf-8")
    assert main(["check", str(model)]) == 0
    assert main(["check", str(model), "--strict"]) == 1


def test_init_scaffolds_a_valid_project(tmp_path, capsys):
    assert main(["init", str(tmp_path / "docs"), "--lang", "es"]) == 0
    assert "language: es" in (tmp_path / "docs" / "project.yaml").read_text(encoding="utf-8")
    assert main(["check", str(tmp_path / "docs" / "project.yaml")]) == 0
    assert main(["init", str(tmp_path / "docs")]) == 1          # never overwrites silently
    assert "already exists" in capsys.readouterr().err
    assert main(["init", str(tmp_path / "docs"), "--force"]) == 0


def test_render_writes_svg_and_rejects_bad_requests(tmp_path, capsys):
    out = tmp_path / "m1.svg"
    assert main(["render", "usecase", str(EXAMPLE / "project.yaml"), "--module", "M1", "-o", str(out)]) == 0
    assert "Send confirmation" in out.read_text(encoding="utf-8")
    assert main(["render", "context", str(EXAMPLE / "project.yaml"), "-o", str(tmp_path / "context.svg")]) == 0
    assert main(["render", "usecase", str(EXAMPLE / "project.yaml"), "--module", "M9", "-o", str(out)]) == 1
    assert "module 'M9' is not defined" in capsys.readouterr().err
    assert main(["render", "usecase", str(EXAMPLE / "project.yaml"), "-o", str(tmp_path / "x.jpg")]) == 1


@pytest.mark.skipif(not HAS_CONVERTER, reason="no SVG converter installed")
def test_build_the_scaffold_and_inspect_it(tmp_path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    assert main(["build", str(tmp_path / "document.yaml")]) == 0
    built = tmp_path / "out" / "document.docx"
    assert built.is_file()
    capsys.readouterr()
    assert main(["inspect", str(built)]) == 0
    shown = capsys.readouterr().out
    assert "tables: 4  figures: 1" in shown and "1. Introduction" in shown and "[above] Figure 1. Use case diagram." in shown


@pytest.mark.skipif(not (HAS_CONVERTER and HAS_OFFICE), reason="LibreOffice or poppler not installed")
def test_preview_renders_pages(tmp_path, capsys):
    assert main(["build", str(EXAMPLE / "document.yaml"), "-o", str(tmp_path / "example.docx")]) == 0
    assert main(["preview", str(tmp_path / "example.docx"), "--out-dir", str(tmp_path / "preview")]) == 0
    assert len(list((tmp_path / "preview").glob("example-page-*.png"))) >= 5
    assert (tmp_path / "preview" / "example.pdf").is_file()


def test_doctor_lists_the_tools(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "python-docx" in out and "PyYAML" in out
