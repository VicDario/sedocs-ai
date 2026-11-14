"""Read a generated (or any) Word document back and report its structure and loose ends."""
from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.oxml.ns import qn

CAPTION = re.compile(r"^(\S+) (\d+)\. ")


def _text(element) -> str:
    return "".join(t.text or "" for t in element.iter(qn("w:t")))


def inspect_docx(path: str | Path) -> dict:
    doc = docx.Document(str(path))
    body = list(doc.element.body)
    # Bibliography blocks wrap their paragraphs in a content control: look inside them too.
    flat = []
    for element in body:
        if element.tag == qn("w:sdt"):
            flat.extend(element.iter(qn("w:p")))
        else:
            flat.append(element)

    headings, captions, problems = [], [], []
    numbers: dict[str, int] = {}
    for index, element in enumerate(flat):
        if element.tag != qn("w:p"):
            continue
        text = _text(element)
        style = None
        properties = element.find(qn("w:pPr"))
        if properties is not None and properties.find(qn("w:pStyle")) is not None:
            style = properties.find(qn("w:pStyle")).get(qn("w:val"))
        # Style ids are localised by Word and lose their non-ASCII letters: Heading1, Ttulo1 (Título),
        # Titre1, berschrift1 (Überschrift).
        if style and re.fullmatch(r"(Heading|Ttulo|Titre|berschrift)\s?(\d)", style):
            headings.append((int(style[-1]), text))
        has_sequence = any("SEQ" in (i.text or "") for i in element.iter(qn("w:instrText")))
        match = CAPTION.match(text)
        if match and has_sequence:
            label, number = match.group(1), int(match.group(2))
            numbers[label] = numbers.get(label, 0) + 1
            if number != numbers[label]:
                problems.append(f"caption out of sequence: '{text[:60]}'")
            before = flat[index - 1] if index else None
            after = flat[index + 1] if index + 1 < len(flat) else None

            def is_object(el) -> bool:
                return el is not None and (el.tag == qn("w:tbl") or el.find(".//" + qn("w:drawing")) is not None)

            position = "above" if is_object(after) else "below" if is_object(before) else "detached"
            if position == "detached":
                problems.append(f"caption not next to a table or figure: '{text[:60]}'")
            captions.append({"label": label, "number": number, "text": text, "position": position})
        if "{{" in text or "{cite:" in text:
            problems.append(f"unresolved marker in: '{text[:70]}'")

    cited = set()
    for instr in doc.element.body.iter(qn("w:instrText")):
        found = re.findall(r"CITATION\s+(\w+)((?:\s+\\m\s+\w+)*)", instr.text or "")
        for first, rest in found:
            cited.add(first)
            cited.update(re.findall(r"\\m\s+(\w+)", rest))
    sources = set()
    for part in doc.part.package.iter_parts():
        if str(part.partname).startswith("/customXml/item") and b"b:Sources" in part.blob:
            sources.update(re.findall(r"<b:Tag>([^<]+)</b:Tag>", part.blob.decode("utf-8", "replace")))
    for missing in sorted(cited - sources):
        problems.append(f"citation of '{missing}' has no entry in the source list")

    figures = sum(len(element.findall(".//" + qn("w:drawing"))) for element in flat)
    return {
        "title": doc.core_properties.title or "", "author": doc.core_properties.author or "",
        "headings": headings, "tables": len(doc.tables), "figures": figures, "captions": captions,
        "cited": sorted(cited), "sources": sorted(sources), "problems": problems,
    }
