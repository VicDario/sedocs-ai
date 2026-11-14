import re
import shutil
from pathlib import Path

import docx
import pytest
import yaml
from docx.oxml.ns import qn

from sedocs_ai.docinfo import inspect_docx
from sedocs_ai.document import BuildError, build_document

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "harbor-clinic"
HAS_CONVERTER = any(shutil.which(tool) for tool in ("rsvg-convert", "inkscape", "magick"))


def body_text(path) -> list[str]:
    doc = docx.Document(str(path))
    return ["".join(t.text or "" for t in p.iter(qn("w:t"))) for p in doc.element.body.iter(qn("w:p"))]


def write_spec(tmp_path, spec: dict, name="doc.yaml") -> Path:
    shutil.copy(EXAMPLE / "project.yaml", tmp_path / "project.yaml")
    path = tmp_path / name
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def base_spec() -> dict:
    return {
        "document": {"title": "Requirements Specification", "date": "2026-03-02", "version": "0.3",
                     "responsible": [{"name": "Jane Doe", "role": "Business analyst"}, "John Roe"]},
        "model": "project.yaml",
        "sources": [{"id": "cockburn", "type": "book", "authors": ["Cockburn, Alistair"], "year": 2001,
                     "title": "Writing effective use cases", "publisher": "Addison-Wesley"}],
        "sections": [
            {"heading": "Scope", "content": ["Plain text with **bold**, *italic* and a citation {cite:cockburn}.",
                                             {"requirements_table": "functional"}]},
            {"heading": "Details", "sections": [{"heading": "Use cases", "content": [
                {"use_case_table": {"module": "M1", "title": "Scheduling use cases"}}, {"use_case_card": "UC-1.01"}]}]},
            {"heading": "References", "content": [{"references": True}]},
        ],
    }


def test_cover_is_generic_and_states_responsible_and_date(tmp_path):
    report = build_document(write_spec(tmp_path, base_spec()), tmp_path / "out.docx")
    lines = body_text(report.output)
    assert "Requirements Specification" in lines
    assert "Appointment Booking System" in lines            # project name comes from the model
    assert "Harbor Vet Clinic" in lines                     # and so does the organisation
    assert "Responsible: Jane Doe (Business analyst), John Roe" in lines
    assert "Date: 2026-03-02" in lines and "Version: 0.3" in lines
    assert not any(line.startswith("Status:") for line in lines)   # optional fields stay out when empty
    props = docx.Document(str(report.output)).core_properties
    assert props.author == "Jane Doe, John Roe" and props.title == "Requirements Specification"


def test_cover_requires_title_responsible_and_date(tmp_path):
    spec = base_spec()
    spec["document"] = {"title": "Only a title"}
    with pytest.raises(BuildError, match="document.responsible, document.date"):
        build_document(write_spec(tmp_path, spec), tmp_path / "out.docx")


def test_structure_captions_and_citations(tmp_path):
    report = build_document(write_spec(tmp_path, base_spec()), tmp_path / "out.docx")
    info = inspect_docx(report.output)
    assert info["headings"] == [(1, "1. Scope"), (1, "2. Details"), (2, "2.1 Use cases"), (1, "3. References")]
    assert [(c["label"], c["number"], c["position"]) for c in info["captions"]] == [
        ("Table", 1, "above"), ("Table", 2, "above"), ("Table", 3, "above")]
    assert info["captions"][2]["text"] == "Table 3. Use case UC-1.01: Book appointment."
    assert info["cited"] == ["cockburn"] == info["sources"] and info["problems"] == []
    assert (report.tables, report.figures, report.cited, report.warnings) == (3, 0, ["cockburn"], [])
    lines = body_text(report.output)
    assert "Plain text with bold, italic and a citation (Cockburn, 2001)." in lines
    assert "Cockburn, A. (2001). Writing effective use cases. Addison-Wesley." in lines
    assert "1. The receptionist searches for the pet by name or by client." in lines


def test_profile_controls_language_caption_position_and_source_line(tmp_path):
    spec = base_spec()
    spec["document"]["language"] = "es"
    spec["document"]["date"] = __import__("datetime").date(2026, 3, 2)
    spec["profile"] = {"captions": {"position": "below", "source_line": True}, "headings": {"numbered": False},
                       "citations": {"word_fields": False}}
    report = build_document(write_spec(tmp_path, spec), tmp_path / "out.docx")
    lines = body_text(report.output)
    assert "Responsable: Jane Doe (Business analyst), John Roe" in lines and "Fecha: 2 de marzo de 2026" in lines
    assert "Fuente: elaboración propia (2026)." in lines
    info = inspect_docx(report.output)
    assert info["headings"][0] == (1, "Scope")
    assert {c["position"] for c in info["captions"]} == {"below"} and info["captions"][0]["label"] == "Tabla"
    assert info["cited"] == []          # plain-text citations, no Word fields


def test_template_placeholders_and_content_marker(tmp_path):
    template = docx.Document()
    template.add_paragraph("ACME Corp internal template")
    template.add_paragraph("{{title}} for {{project}}")
    split = template.add_paragraph()
    split.add_run("Owner: {{respon")
    split.add_run("sible}} on {{date}}")
    template.add_paragraph("{{content}}")
    template.add_paragraph("Closing page of the template")
    template.sections[0].footer.paragraphs[0].text = "{{title}} v{{version}}"
    template.save(str(tmp_path / "template.docx"))
    spec = base_spec()
    spec["profile"] = {"template": "template.docx"}
    report = build_document(write_spec(tmp_path, spec), tmp_path / "out.docx")
    lines = [line for line in body_text(report.output) if line]
    assert lines[:3] == ["ACME Corp internal template", "Requirements Specification for Appointment Booking System",
                         "Owner: Jane Doe (Business analyst), John Roe on 2026-03-02"]
    assert lines[3] == "1. Scope" and lines[-1] == "Closing page of the template"
    assert not any("{{" in line for line in lines)
    assert "Responsible: Jane Doe (Business analyst), John Roe" not in lines   # no built-in cover over a template
    footer = docx.Document(str(report.output)).sections[0].footer.paragraphs[0].text
    assert footer == "Requirements Specification v0.3"


@pytest.mark.parametrize("change, message", [
    (lambda s: s["sections"][0]["content"].append("See {cite:nobody}."), "unknown source"),
    (lambda s: s["sections"][0]["content"].append({"chart": {}}), "unknown block 'chart'"),
    (lambda s: s["sections"][0]["content"].append({"use_case_card": "UC-9.99"}), "is not defined in the model"),
    (lambda s: s["sections"].append({"content": ["no heading"]}), "needs a 'heading'"),
    (lambda s: s.pop("sections"), "has no 'sections'"),
    (lambda s: s["sections"][0]["content"].append({"table": {"title": "T", "columns": ["A", "B"], "rows": [["1"]]}}),
     "1 cells for 2 columns"),
    (lambda s: s.__setitem__("profile", {"colours": {}}), "unknown profile setting 'colours'"),
])
def test_mistakes_in_the_spec_are_reported_clearly(tmp_path, change, message):
    spec = base_spec()
    change(spec)
    with pytest.raises(BuildError, match=re.escape(message)):
        build_document(write_spec(tmp_path, spec), tmp_path / "out.docx")


def test_model_blocks_need_a_model_and_uncited_sources_are_flagged(tmp_path):
    spec = base_spec()
    spec.pop("model")
    spec["document"]["project"] = "Standalone"
    with pytest.raises(BuildError, match="needs a project model"):
        build_document(write_spec(tmp_path, spec), tmp_path / "out.docx")
    spec = base_spec()
    spec["sources"].append({"id": "unused", "organization": "Somebody", "title": "Never cited", "year": 2020})
    report = build_document(write_spec(tmp_path, spec), tmp_path / "out.docx")
    assert report.warnings == ["sources never cited: unused"]
    assert not any("Never cited" in line for line in body_text(report.output))


@pytest.mark.skipif(not HAS_CONVERTER, reason="no SVG converter installed")
def test_example_document_builds_end_to_end(tmp_path):
    report = build_document(EXAMPLE / "document.yaml", tmp_path / "example.docx")
    info = inspect_docx(report.output)
    assert (report.tables, report.figures, report.warnings) == (8, 3, [])
    assert info["problems"] == [] and info["cited"] == ["cockburn", "omguml"]
    assert [c["label"] for c in info["captions"]].count("Figure") == 3
    assert (tmp_path / ".sedocs" / "example-figure1.svg").is_file()


def test_use_case_cards_pass_their_source_option_to_every_card(tmp_path):
    spec = base_spec()
    spec["profile"] = {"captions": {"source_line": True}}
    spec["sections"] = [{"heading": "Cards", "content": [{"use_case_cards": {"module": "M2", "source": False}}]}]
    silenced = build_document(write_spec(tmp_path, spec), tmp_path / "off.docx")
    assert silenced.tables == 3
    assert not any(line.startswith("Source:") for line in body_text(silenced.output))
    spec["sections"][0]["content"] = [{"use_case_cards": {"module": "M2", "source": "Source: workshop notes."}}]
    custom = build_document(write_spec(tmp_path, spec), tmp_path / "custom.docx")
    assert body_text(custom.output).count("Source: workshop notes.") == 3
    spec["sections"][0]["content"] = [{"use_case_cards": {"module": "M2", "title": "One title for all"}}]
    with pytest.raises(BuildError, match="use_case_cards: unknown option"):
        build_document(write_spec(tmp_path, spec), tmp_path / "bad.docx")
