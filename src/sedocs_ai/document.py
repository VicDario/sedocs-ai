"""Build a Word document from a document spec, a profile and (optionally) the project model.

The spec lists the cover data, the sections and their content blocks. Blocks are either written by
hand (paragraph, bullets, table, figure) or generated from the project model (requirement tables,
use case tables and cards, diagrams). Tables and figures are numbered with Word caption fields and
citations are Word citation fields backed by the source list of the document.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import docx
import yaml
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor, Twips

from . import citations, i18n
from .context import render_context_diagram
from .model import ModelError, Project, load_project, validate
from .profile import ProfileError, load_profile
from .raster import RenderError, png_size, svg_to_png
from .usecase import DiagramError, render_use_case_diagram

INLINE = re.compile(r"(\{cite:[^}]+\}|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)")
PLACEHOLDERS = ("title", "project", "organization", "responsible", "date", "version", "status")
PAGE_SIZES = {"letter": (Inches(8.5), Inches(11)), "a4": (Cm(21), Cm(29.7))}
ALIGN = {"justify": WD_ALIGN_PARAGRAPH.JUSTIFY, "left": WD_ALIGN_PARAGRAPH.LEFT}
MODEL_BLOCKS = ("actors_table", "requirements_table", "business_rules_table", "use_case_table", "use_case_card",
                "use_case_cards", "traceability_table")
HEADING_SIZES = {1: 16, 2: 13, 3: 11.5}     # points, for the three heading levels
DIAGRAM_PX_PER_INCH = 200     # diagrams are drawn at this scale, so their text prints at about 7 pt
BLOCKS = ("paragraph", "bullets", "numbered", "table", "figure", "page_break", "references") + MODEL_BLOCKS


class BuildError(Exception):
    """The document cannot be built from the spec as written."""


@dataclass
class BuildReport:
    output: Path
    tables: int = 0
    figures: int = 0
    cited: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _field_run(paragraph, char_type: str | None = None, instr: str | None = None):
    run = paragraph.add_run()
    if char_type:
        char = OxmlElement("w:fldChar")
        char.set(qn("w:fldCharType"), char_type)
        run._r.append(char)
    if instr is not None:
        text = OxmlElement("w:instrText")
        text.set(qn("xml:space"), "preserve")
        text.text = instr
        run._r.append(text)
    return run


def _field(paragraph, instr: str, result: str, dirty: bool = False):
    """Complex field with a precomputed result; returns the run that holds the result."""
    begin = _field_run(paragraph, "begin")
    if dirty:
        begin._r[-1].set(qn("w:dirty"), "true")
    _field_run(paragraph, instr=instr)
    _field_run(paragraph, "separate")
    shown = paragraph.add_run(result)
    _field_run(paragraph, "end")
    return shown


def _shade(cell, fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _borders(cell, color: str) -> None:
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        edge = OxmlElement(f"w:{side}")
        for key, value in (("val", "single"), ("sz", "4"), ("space", "0"), ("color", color)):
            edge.set(qn(f"w:{key}"), value)
        borders.append(edge)
    cell._tc.get_or_add_tcPr().append(borders)


def _set_style_font(style, name: str, size: float | None = None, bold: bool | None = None,
                    color: str | None = None, italic: bool | None = None) -> None:
    style.font.name = name
    fonts = style.element.rPr.find(qn("w:rFonts"))
    for theme in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):  # theme fonts would win over the name
        fonts.attrib.pop(qn(f"w:{theme}"), None)
    fonts.set(qn("w:eastAsia"), name)
    fonts.set(qn("w:cs"), name)
    if size is not None:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic
    if color is not None:
        style.font.color.rgb = RGBColor.from_string(color)


class _Builder:
    def __init__(self, spec: dict, base_dir: Path, output: Path):
        self.spec, self.base_dir, self.output = spec, base_dir, output
        try:
            self.project: Project | None = load_project(base_dir / str(spec["model"])) if spec.get("model") else None
            self.profile = load_profile(spec.get("profile"), base_dir)
        except (ModelError, ProfileError) as exc:
            raise BuildError(str(exc)) from exc
        if self.project is not None:
            errors = [issue for issue in validate(self.project) if issue.level == "error"]
            if errors:
                raise BuildError(f"the project model has {len(errors)} error(s); run 'sedocs check' on it. "
                                 f"First: {errors[0].message}")
        meta = spec.get("document") or {}
        if not isinstance(meta, dict):
            raise BuildError("'document' must be a mapping with the cover data")
        try:
            self.lang = i18n.language(meta.get("language") or self.profile["language"]
                                      or (self.project.language if self.project else "en"))
            self.sources = {}
            tags: dict[str, str] = {}
            for source in (citations.normalise(raw) for raw in spec.get("sources") or []):
                if source["id"] in self.sources:
                    raise BuildError(f"source id '{source['id']}' is used more than once")
                clash = tags.setdefault(citations.tag(source["id"]), source["id"])
                if clash != source["id"]:   # Word identifies sources by letters and digits only
                    raise BuildError(f"source ids '{clash}' and '{source['id']}' become the same Word tag; rename one")
                self.sources[source["id"]] = source
        except (ValueError, citations.CitationError) as exc:
            raise BuildError(str(exc)) from exc
        self.meta = self._cover_data(meta)
        self.report = BuildReport(output)
        self.counters = {"table": 0, "figure": 0}
        self.numbering: list[int] = []
        self.colors = self.profile["colors"]

    # ------------------------------------------------------------------ cover data
    def _cover_data(self, meta: dict) -> dict:
        project = str(meta.get("project") or (self.project.name if self.project else ""))
        people = []
        listed = meta.get("responsible") or []
        for person in (listed if isinstance(listed, (list, tuple)) else [listed]):   # one person may be given alone
            if isinstance(person, dict):
                name, role = str(person.get("name") or "").strip(), str(person.get("role") or "").strip()
            else:
                name, role = str(person).strip(), ""
            if name:
                people.append((name, role))
        missing = [key for key, value in (("title", meta.get("title")), ("project", project),
                                          ("responsible", people), ("date", meta.get("date"))) if not value]
        if missing:
            raise BuildError("the document needs " + ", ".join(f"document.{m}" for m in missing)
                             + " (responsible is a list of people with 'name' and an optional 'role')")
        date = meta["date"]
        year = date.year if isinstance(date, (_dt.date, _dt.datetime)) else (re.findall(r"\d{4}", str(date)) or [""])[0]
        return {
            "title": str(meta["title"]), "project": project,
            "organization": str(meta.get("organization") or (self.project.organization if self.project else "")),
            "people": people,
            "responsible": ", ".join(f"{name} ({role})" if role else name for name, role in people),
            "date": i18n.format_date(date, self.lang), "year": str(year),
            "version": str(meta.get("version") or ""), "status": str(meta.get("status") or ""),
        }

    # ------------------------------------------------------------------ document set-up
    def build(self) -> BuildReport:
        template = self.profile["template"]
        self.doc = docx.Document(str(template)) if template else docx.Document()
        self.body = self.doc.element.body
        first_new = len(self.body) - 1          # everything added from here on is ours
        if not template:
            self._page_setup()
            self._base_styles()
        section = self.doc.sections[-1]
        self.usable = section.page_width - section.left_margin - section.right_margin   # EMU

        if self.profile["cover"]["enabled"]:
            self._cover()
        if self.profile["toc"]:
            self._toc()
        sections = self.spec.get("sections") or []
        if not sections:
            raise BuildError("the document has no 'sections'")
        for item in sections:
            self._section(item, 1)

        self._fill_placeholders()
        self._move_to_marker(first_new)
        if self.sources:
            self._install_sources()
        uncited = [sid for sid in self.sources if sid not in self.report.cited]
        if uncited:
            self.report.warnings.append("sources never cited: " + ", ".join(uncited))
        props = self.doc.core_properties
        props.title = self.meta["title"]
        props.author = ", ".join(name for name, _ in self.meta["people"])
        props.last_modified_by = props.author
        props.comments = ""
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(self.output))
        self.report.tables, self.report.figures = self.counters["table"], self.counters["figure"]
        return self.report

    def _page_setup(self) -> None:
        width, height = PAGE_SIZES[self.profile["page"]["size"]]
        margin = Cm(float(self.profile["page"]["margin_cm"]))
        for section in self.doc.sections:
            section.page_width, section.page_height = width, height
            section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = margin

    def _base_styles(self) -> None:
        font, size, accent = self.profile["fonts"]["body"], float(self.profile["fonts"]["size"]), self.colors["accent"]
        styles = self.doc.styles
        _set_style_font(styles["Normal"], font, size)
        for level, points in HEADING_SIZES.items():
            style = styles[f"Heading {level}"]
            _set_style_font(style, font, points, bold=True, color=accent, italic=False)
            style.paragraph_format.space_before = Pt(18 if level == 1 else 12)
            style.paragraph_format.space_after = Pt(6)
        _set_style_font(styles["Caption"], font, float(self.profile["captions"]["size"]), bold=False,
                        color="333333", italic=True)

    # ------------------------------------------------------------------ text
    def _has_style(self, name: str) -> bool:
        try:
            self.doc.styles[name]
            return True
        except KeyError:
            return False

    def _paragraph(self, text: str = "", style: str | None = None, body_format: bool = True, parent=None):
        paragraph = (parent or self.doc).add_paragraph(style=style if style and self._has_style(style) else None)
        if body_format:
            settings = self.profile["paragraph"]
            fmt = paragraph.paragraph_format
            fmt.alignment = ALIGN.get(settings["align"], WD_ALIGN_PARAGRAPH.JUSTIFY)
            fmt.line_spacing = float(settings["line_spacing"])
            fmt.space_after = Pt(float(settings["space_after"]))
        if text:
            self._inline(paragraph, text)
        return paragraph

    def _inline(self, paragraph, text: str, size: float | None = None, bold: bool | None = None,
                color: str | None = None) -> None:
        """Write text with **bold**, *italic* and {cite:id} markers."""
        def style(run, italic=None, strong=None):
            if size:
                run.font.size = Pt(size)
            if strong or bold:
                run.bold = True
            if italic:
                run.italic = True
            if color:
                run.font.color.rgb = RGBColor.from_string(color)

        for part in INLINE.split(str(text)):
            if not part:
                continue
            if part.startswith("{cite:"):
                style(self._citation(paragraph, part[6:-1]))
            elif part.startswith("**"):
                style(paragraph.add_run(part[2:-2]), strong=True)
            elif part.startswith("*") and len(part) > 2:
                style(paragraph.add_run(part[1:-1]), italic=True)
            else:
                style(paragraph.add_run(part))

    def _citation(self, paragraph, ids_text: str):
        ids = [item.strip() for item in ids_text.split(",") if item.strip()]
        unknown = [sid for sid in ids if sid not in self.sources]
        if unknown or not ids:
            raise BuildError(f"citation of unknown source(s): {', '.join(unknown) or ids_text!r}; "
                             f"defined sources: {', '.join(self.sources) or 'none'}")
        for sid in ids:
            if sid not in self.report.cited:
                self.report.cited.append(sid)
        shown = "(" + "; ".join(citations.in_text(self.sources[sid]) for sid in ids) + ")"
        if not self.profile["citations"]["word_fields"]:
            return paragraph.add_run(shown)
        instr = f" CITATION {citations.tag(ids[0])}" + "".join(f" \\m {citations.tag(sid)}" for sid in ids[1:])
        return _field(paragraph, f"{instr} \\l {i18n.t(self.lang, 'lcid')} ", shown)

    def _heading(self, text: str, level: int) -> None:
        level = max(1, min(level, 3))
        self.numbering = self.numbering[:level]
        while len(self.numbering) < level:
            self.numbering.append(0)
        self.numbering[level - 1] += 1
        if self.profile["headings"]["numbered"]:
            text = ".".join(str(n) for n in self.numbering) + ("." if level == 1 else "") + " " + text
        style = f"Heading {level}"
        if self._has_style(style):
            paragraph = self.doc.add_paragraph(text, style=style)
        else:  # template without heading styles: emphasised paragraph
            paragraph = self.doc.add_paragraph()
            run = paragraph.add_run(text)
            run.bold = True
            run.font.size = Pt(HEADING_SIZES[level])
        paragraph.paragraph_format.keep_with_next = True

    # ------------------------------------------------------------------ cover and contents
    def _cover(self) -> None:
        meta, accent, muted = self.meta, self.colors["accent"], self.colors["muted"]
        logo = self.profile["cover"]["logo"]
        if logo:
            self.doc.add_picture(str(logo), width=Inches(1.6))
        top = self._paragraph(body_format=False)
        top.paragraph_format.space_before = Pt(110 if logo else 170)
        if meta["organization"]:
            self._inline(top, meta["organization"], size=13, color=muted)
        title = self._paragraph(body_format=False)
        title.paragraph_format.space_before = Pt(6)
        title.paragraph_format.space_after = Pt(6)
        self._inline(title, meta["title"], size=30, bold=True, color=accent)
        project = self._paragraph(body_format=False)
        self._inline(project, meta["project"], size=16, color="333333")
        project.paragraph_format.space_after = Pt(18)
        border = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for key, value in (("val", "single"), ("sz", "8"), ("space", "12"), ("color", accent)):
            bottom.set(qn(f"w:{key}"), value)
        border.append(bottom)
        project._p.get_or_add_pPr().append(border)
        for key in ("responsible", "date", "version", "status"):
            if not meta[key]:
                continue
            line = self._paragraph(body_format=False)
            line.paragraph_format.space_after = Pt(4)
            self._inline(line, i18n.t(self.lang, key) + ": ", size=11, bold=True, color="333333")
            self._inline(line, meta[key], size=11, color="333333")
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def _toc(self) -> None:
        heading = self._paragraph(body_format=False)
        self._inline(heading, i18n.t(self.lang, "contents"), size=16, bold=True, color=self.colors["accent"])
        entry = self._paragraph(body_format=False)
        _field(entry, ' TOC \\o "1-3" \\h \\z \\u ', i18n.t(self.lang, "toc_hint"), dirty=True)
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ------------------------------------------------------------------ sections and blocks
    def _section(self, item: dict, level: int) -> None:
        if not isinstance(item, dict) or not item.get("heading"):
            raise BuildError(f"every section needs a 'heading': {item!r}")
        unknown = set(item) - {"heading", "content", "sections", "page_break"}
        if unknown:
            raise BuildError(f"section '{item['heading']}': unknown key(s) {', '.join(sorted(unknown))}")
        if level > len(HEADING_SIZES):
            raise BuildError(f"section '{item['heading']}': sections nest up to three levels")
        if item.get("page_break"):
            self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        self._heading(str(item["heading"]), level)
        for block in item.get("content") or []:
            self._block(block, str(item["heading"]))
        for child in item.get("sections") or []:
            self._section(child, level + 1)

    def _block(self, block, where: str) -> None:
        if isinstance(block, str):
            self._paragraph(block)
            return
        if not isinstance(block, dict) or len(block) != 1:
            raise BuildError(f"section '{where}': every content block is text or a mapping with one key, found {block!r}")
        kind, value = next(iter(block.items()))
        if kind not in BLOCKS:
            raise BuildError(f"section '{where}': unknown block '{kind}' (known: {', '.join(BLOCKS)})")
        if kind in MODEL_BLOCKS and self.project is None:
            raise BuildError(f"section '{where}': block '{kind}' needs a project model; set 'model:' in the spec")
        try:
            getattr(self, "_b_" + kind)(value)
        except (DiagramError, RenderError, citations.CitationError) as exc:
            raise BuildError(f"section '{where}', block '{kind}': {exc}") from exc
        except (TypeError, ValueError) as exc:     # a value of the wrong kind, such as text where a number goes
            raise BuildError(f"section '{where}', block '{kind}': a value has the wrong type ({exc})") from exc

    def _b_paragraph(self, value) -> None:
        self._paragraph(str(value))

    def _b_bullets(self, value) -> None:
        for item in value or []:
            if self._has_style("List Bullet"):
                self._paragraph(str(item), style="List Bullet").paragraph_format.space_after = Pt(3)
            else:
                self._paragraph("• " + str(item)).paragraph_format.space_after = Pt(3)

    def _b_numbered(self, value) -> None:
        for number, item in enumerate(value or [], 1):
            paragraph = self._paragraph(f"{number}. {item}")
            paragraph.paragraph_format.left_indent = Inches(0.3)
            paragraph.paragraph_format.first_line_indent = Inches(-0.3)
            paragraph.paragraph_format.space_after = Pt(3)

    def _b_page_break(self, value) -> None:
        if value:
            self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ------------------------------------------------------------------ captions
    def _caption(self, kind: str, title: str, keep_next: bool):
        self.counters[kind] += 1
        label = i18n.t(self.lang, kind)
        paragraph = self._paragraph(style="Caption", body_format=False)
        fmt = paragraph.paragraph_format
        fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER if kind == "figure" else WD_ALIGN_PARAGRAPH.LEFT
        fmt.space_before, fmt.space_after, fmt.keep_with_next = Pt(8), Pt(4), keep_next
        size = float(self.profile["captions"]["size"])
        runs = [paragraph.add_run(label + " "),
                _field(paragraph, f" SEQ {label} \\* ARABIC ", str(self.counters[kind])),
                ]
        for run in runs:
            run.italic, run.font.size = True, Pt(size)
        self._inline(paragraph, ". " + title.rstrip(".") + ".", size=size)
        for run in paragraph.runs:
            run.italic = True
        return paragraph

    def _source_line(self, kind: str, override) -> None:
        setting = override if override is not None else self.profile["captions"]["source_line"]
        if not setting:
            return
        text = i18n.t(self.lang, "source_own", year=self.meta["year"]) if setting is True or setting == "own" else str(setting)
        paragraph = self._paragraph(style="Caption", body_format=False)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if kind == "figure" else WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_before, paragraph.paragraph_format.space_after = Pt(3), Pt(10)
        self._inline(paragraph, text, size=float(self.profile["captions"]["size"]))
        for run in paragraph.runs:
            run.italic = True

    def _captioned(self, kind: str, title: str, source, draw) -> None:
        """Caption above or below the table or figure, as the profile says, and the source line last."""
        above = self.profile["captions"]["position"] == "above"
        if above:
            self._caption(kind, title, keep_next=True)
        draw(keep_with_caption=not above)
        if not above:
            self._caption(kind, title, keep_next=False)
        self._source_line(kind, source)
        has_source = bool(source if source is not None else self.profile["captions"]["source_line"])
        if kind == "table" and above and not has_source:
            # Nothing follows the table: a small empty paragraph separates it from what comes next.
            spacer = self._paragraph(body_format=False)
            spacer.paragraph_format.space_before = spacer.paragraph_format.space_after = Pt(0)
            spacer.paragraph_format.line_spacing = Pt(8)

    # ------------------------------------------------------------------ tables
    def _widths(self, columns: list[str], rows: list[list[str]], widths) -> list[int]:
        total = int(self.usable / 635)          # EMU to twentieths of a point
        if widths:
            if len(widths) != len(columns):
                raise BuildError(f"table '{columns}': {len(widths)} widths for {len(columns)} columns")
            weights = [float(w) for w in widths]
        else:
            weights = []
            for index, header in enumerate(columns):
                longest = max([len(header)] + [max((len(line) for line in str(row[index]).split("\n")), default=0) for row in rows])
                weights.append(min(max(longest, 7), 55))
        scale = total / sum(weights)
        result = [int(w * scale) for w in weights]
        result[-1] += total - sum(result)
        return result

    def _table(self, columns: list[str], rows: list[list], widths=None, center=(), label_cols=()) -> None:
        columns = [str(c) for c in columns]
        rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
        for row in rows:
            if len(row) != len(columns):
                raise BuildError(f"table '{', '.join(columns)}': a row has {len(row)} cells for {len(columns)} columns")
        twips = self._widths(columns, rows, widths)
        total = sum(twips)
        size = float(self.profile["tables"]["font_size"])
        table = self.doc.add_table(rows=0, cols=len(columns))
        table.autofit = False
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        properties = table._tbl.tblPr
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        properties.append(layout)
        for grid, width in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), twips):
            grid.set(qn("w:w"), str(width))
        wide = float(self.profile["tables"]["wide_percent"]) / 100 * total

        def add_row(values, header=False):
            row = table.add_row()
            row_properties = row._tr.get_or_add_trPr()
            row_properties.append(OxmlElement("w:cantSplit"))
            if header:
                row_properties.append(OxmlElement("w:tblHeader"))
            for index, (cell, value, width) in enumerate(zip(row.cells, values, twips)):
                cell.width = Twips(width)
                _borders(cell, self.colors["border"])
                align = OxmlElement("w:vAlign")
                align.set(qn("w:val"), "center")
                cell._tc.get_or_add_tcPr().append(align)
                label = not header and index in label_cols
                if header:
                    _shade(cell, self.colors["accent"])
                elif label:
                    _shade(cell, self.colors["label_fill"])
                paragraph = cell.paragraphs[0]
                for number, line in enumerate(value.split("\n")):
                    if number:
                        paragraph = cell.add_paragraph()
                    fmt = paragraph.paragraph_format
                    fmt.space_before = fmt.space_after = Pt(2)
                    fmt.line_spacing = 1.0
                    fmt.keep_with_next = header
                    if header or index in center:
                        fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif self.profile["tables"]["justify_wide"] and width >= wide and not label:
                        fmt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    else:
                        fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    self._inline(paragraph, line, size=size, bold=header or label,
                                 color=self.colors["header_text"] if header else None)

        if any(columns):
            add_row(columns, header=True)
        for row in rows:
            add_row(row)
        self._last_table = table

    def _keep_last_row_with_next(self) -> None:
        for cell in self._last_table.rows[-1].cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.keep_with_next = True

    def _titled_table(self, title: str, columns, rows, source=None, **options) -> None:
        def draw(keep_with_caption: bool) -> None:
            self._table(columns, rows, **options)
            if keep_with_caption:
                self._keep_last_row_with_next()
        self._captioned("table", title, source, draw)

    def _b_table(self, value) -> None:
        if not isinstance(value, dict) or not value.get("title") or not value.get("columns"):
            raise BuildError("a table block needs 'title', 'columns' and 'rows'")
        unknown = set(value) - {"title", "columns", "rows", "widths", "center", "source"}
        if unknown:
            raise BuildError(f"table '{value['title']}': unknown key(s) {', '.join(sorted(unknown))}")
        self._titled_table(str(value["title"]), value["columns"], value.get("rows") or [], value.get("source"),
                           widths=value.get("widths"), center=tuple(value.get("center") or ()))

    # ------------------------------------------------------------------ figures
    def _b_figure(self, value) -> None:
        if not isinstance(value, dict) or not value.get("title") or not (value.get("path") or value.get("diagram")):
            raise BuildError("a figure block needs 'title' and either 'path' or 'diagram'")
        unknown = set(value) - {"title", "path", "diagram", "width_in", "source"}
        if unknown:
            raise BuildError(f"figure '{value['title']}': unknown key(s) {', '.join(sorted(unknown))}")
        natural = None
        if value.get("diagram"):
            image, natural = self._render_diagram(value["diagram"], str(value["title"]))
        else:
            image = (self.base_dir / str(value["path"])).resolve()
            if not image.is_file():
                raise BuildError(f"figure '{value['title']}': file not found: {image}")
        limits = self.profile["figures"]
        width = min(float(value.get("width_in") or limits["max_width_in"]), self.usable / 914400)
        if natural and not value.get("width_in"):      # same text size in every diagram, whatever its extent
            width = min(width, natural)
        if image.suffix.lower() == ".png":
            pixels_w, pixels_h = png_size(image)
            width = min(width, float(limits["max_height_in"]) * pixels_w / pixels_h)

        def draw(keep_with_caption: bool) -> None:
            self.doc.add_picture(str(image), width=Inches(width))
            picture = self.doc.paragraphs[-1]
            picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
            picture.paragraph_format.keep_with_next = keep_with_caption
        self._captioned("figure", str(value["title"]), value.get("source"), draw)

    def _render_diagram(self, ref, title: str) -> tuple[Path, float]:
        """PNG of a diagram of the model and its natural width in inches."""
        if self.project is None:
            raise BuildError(f"figure '{title}': a diagram needs a project model; set 'model:' in the spec")
        if isinstance(ref, str):
            options = next((dict(d) for d in self.project.diagrams if str(d.get("id")) == ref), None)
            if options is None:
                raise BuildError(f"figure '{title}': diagram '{ref}' is not defined under 'diagrams' in the model")
        elif isinstance(ref, dict):
            options = dict(ref)
        else:
            raise BuildError(f"figure '{title}': 'diagram' is a diagram id or a mapping with 'type'")
        options.pop("id", None)
        kind = options.pop("type", "usecase")
        if kind == "usecase":
            allowed = {"module", "use_cases", "title", "positions", "neighbors", "show_ids"}
            if set(options) - allowed:
                raise BuildError(f"figure '{title}': unknown diagram option(s) {', '.join(sorted(set(options) - allowed))}")
            svg, crossings = render_use_case_diagram(self.project, **options)
            self.report.warnings += [f"figure '{title}': {c}" for c in crossings]
        elif kind == "context":
            if set(options) - {"title"}:
                raise BuildError(f"figure '{title}': unknown diagram option(s) {', '.join(sorted(set(options) - {'title'}))}")
            svg = render_context_diagram(self.project, options.get("title"))
        else:
            raise BuildError(f"figure '{title}': unknown diagram type '{kind}' (use usecase or context)")
        folder = self.output.parent / ".sedocs"
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{self.output.stem}-figure{self.counters['figure'] + 1}"
        (folder / f"{stem}.svg").write_text(svg, encoding="utf-8")
        drawn = float(re.search(r'<svg[^>]* width="([\d.]+)"', svg).group(1))
        return svg_to_png(folder / f"{stem}.svg", folder / f"{stem}.png"), drawn / DIAGRAM_PX_PER_INCH

    # ------------------------------------------------------------------ model-driven blocks
    def _options(self, block: str, value, default_key: str, allowed: tuple[str, ...]) -> dict:
        """Options of a model block. A bare value stands for `default_key`; unknown options are errors."""
        if isinstance(value, dict):
            options = dict(value)
        else:
            options = {} if value in (True, None) else {default_key: value}
        unknown = set(options) - set(allowed)
        if unknown:
            raise BuildError(f"{block}: unknown option(s) {', '.join(sorted(unknown))} (known: {', '.join(allowed)})")
        return options

    def _names(self, actor_ids: list[str]) -> str:
        names = [(self.project.actor(a) or {"name": a})["name"] for a in actor_ids]
        return ", ".join(names) or i18n.t(self.lang, "none")

    def _label(self, key: str) -> str:
        return i18n.t(self.lang, key)

    def _b_actors_table(self, value) -> None:
        options = self._options("actors_table", value, "title", ("title", "source"))
        rows = [[a["name"], self._label(a["kind"]), a.get("description", "")] for a in self.project.actors]
        self._titled_table(options.get("title") or self._label("actors"),
                           [self._label("actor"), self._label("kind"), self._label("description")], rows,
                           options.get("source"), widths=[22, 14, 64])

    def _b_requirements_table(self, value) -> None:
        options = self._options("requirements_table", value, "kind", ("kind", "title", "source"))
        kind = options.get("kind", "functional")
        if kind == "functional":
            columns = [self._label("id"), self._label("name"), self._label("description"), self._label("actors")]
            rows = [[r["id"], r["name"], r.get("description", ""), self._names(r["actors"])] for r in self.project.functional]
            widths = [10, 22, 48, 20]
        elif kind == "non_functional":
            columns = [self._label("id"), self._label("category"), self._label("name"), self._label("description")]
            rows = [[r["id"], r.get("category", ""), r["name"], r.get("description", "")] for r in self.project.non_functional]
            widths = [11, 17, 22, 50]
        else:
            raise BuildError("requirements_table is 'functional' or 'non_functional'")
        self._titled_table(options.get("title") or self._label("requirements"), columns, rows, options.get("source"),
                           widths=widths, center=(0,))

    def _b_business_rules_table(self, value) -> None:
        options = self._options("business_rules_table", value, "title", ("title", "source"))
        rows = [[r["id"], r.get("description", ""), ", ".join(r["requirements"])] for r in self.project.business_rules]
        self._titled_table(options.get("title") or self._label("business_rules"),
                           [self._label("id"), self._label("rule"), self._label("requirements")], rows,
                           options.get("source"), widths=[10, 66, 24], center=(0,))

    def _selected(self, options: dict) -> list[dict]:
        module = options.get("module")
        if module is not None and self.project.module(str(module)) is None:
            raise BuildError(f"module '{module}' is not defined in the model")
        return self.project.use_cases_of(str(module) if module is not None else None)

    def _b_use_case_table(self, value) -> None:
        options = self._options("use_case_table", value, "module", ("module", "title", "source"))
        rows = [[u["id"], u["name"], self._names(u["actors"]), ", ".join(u["requirements"]),
                 self.project.relations_text(u) or self._label("none")] for u in self._selected(options)]
        self._titled_table(options.get("title") or self._label("use_cases"),
                           [self._label("id"), self._label("use_case"), self._label("actors"),
                            self._label("requirements"), self._label("relations")], rows, options.get("source"),
                           widths=[11, 24, 20, 18, 27], center=(0,))

    def _b_use_case_card(self, value) -> None:
        options = self._options("use_case_card", value, "id", ("id", "title", "source"))
        uc = self.project.use_case(str(options.get("id")))
        if uc is None:
            raise BuildError(f"use case '{options.get('id')}' is not defined in the model")
        module = self.project.module(uc["module"])
        flow = [line if re.match(r"^\d", line) else f"{n}. {line}" for n, line in enumerate(uc["main_flow"], 1)]
        entries = [
            ("id", uc["id"]), ("name", uc["name"]), ("module", module["name"] if module else ""),
            ("actors", self._names(uc["actors"]) if uc["actors"] else ""),
            ("requirements", ", ".join(uc["requirements"])), ("purpose", str(uc.get("purpose") or "")),
            ("description", str(uc.get("description") or "")), ("preconditions", "\n".join(uc["preconditions"])),
            ("postconditions", "\n".join(uc["postconditions"])), ("main_flow", "\n".join(flow)),
            ("alternative_flows", "\n".join(uc["alternative_flows"])), ("exceptions", "\n".join(uc["exceptions"])),
            ("relations", self.project.relations_text(uc)),
        ]
        rows = [[self._label(key), text] for key, text in entries if text]
        title = options.get("title") or f"{self._label('use_case')} {uc['id']}: {uc['name']}"
        self._titled_table(title, ["", ""], rows, options.get("source"), widths=[24, 76], label_cols=(0,))

    def _b_use_case_cards(self, value) -> None:
        # Each card is titled after its own use case, so there is no shared title to set.
        options = self._options("use_case_cards", value, "module", ("module", "source"))
        for uc in self._selected(options):
            card = {"id": uc["id"]}
            if "source" in options:
                card["source"] = options["source"]
            self._b_use_case_card(card)

    def _b_traceability_table(self, value) -> None:
        options = self._options("traceability_table", value, "title", ("title", "source"))
        rows = []
        for req in self.project.functional:
            cases = [u["id"] for u in self.project.use_cases if req["id"] in u["requirements"]]
            rules = [r["id"] for r in self.project.business_rules if req["id"] in r["requirements"]]
            rows.append([req["id"], req["name"], ", ".join(cases) or self._label("none"),
                         ", ".join(rules) or self._label("none")])
        self._titled_table(options.get("title") or self._label("traceability"),
                           [self._label("id"), self._label("requirement"), self._label("use_cases"),
                            self._label("business_rules")], rows, options.get("source"),
                           widths=[11, 37, 28, 24], center=(0,))

    # ------------------------------------------------------------------ references
    def _b_references(self, value) -> None:
        options = value if isinstance(value, dict) else {}
        wanted = list(self.sources) if options.get("include_uncited") else list(self.report.cited)
        entries = sorted((self.sources[sid] for sid in wanted), key=citations.sort_key)
        if not entries:
            self.report.warnings.append("the references block is empty: nothing was cited before it")
            return
        for sid in wanted:
            if sid not in self.report.cited:
                self.report.cited.append(sid)
        container = None
        if self.profile["citations"]["word_fields"]:  # Word treats the block as its bibliography
            sdt, properties, content = OxmlElement("w:sdt"), OxmlElement("w:sdtPr"), OxmlElement("w:sdtContent")
            part = OxmlElement("w:docPartObj")
            gallery = OxmlElement("w:docPartGallery")
            gallery.set(qn("w:val"), "Bibliographies")
            part.append(gallery)
            part.append(OxmlElement("w:docPartUnique"))
            properties.append(part)
            sdt.append(properties)
            sdt.append(content)
            container = content
        for index, source in enumerate(entries):
            paragraph = self._paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.5)
            paragraph.paragraph_format.first_line_indent = Inches(-0.5)
            if container is not None and index == 0:
                _field_run(paragraph, "begin")
                _field_run(paragraph, instr=" BIBLIOGRAPHY ")
                _field_run(paragraph, "separate")
            for text, italic in citations.reference_runs(source, self.lang):
                paragraph.add_run(text).italic = italic or None
            if container is not None:
                if index == len(entries) - 1:
                    _field_run(paragraph, "end")
                container.append(paragraph._p)
        if container is not None:
            self.body.insert(len(self.body) - 1, sdt)

    def _install_sources(self) -> None:
        blob = citations.sources_xml(list(self.sources.values()))
        package = self.doc.part.package
        for part in package.iter_parts():
            if str(part.partname).startswith("/customXml/item") and b"b:Sources" in part.blob:
                part._blob = blob
                return
        existing = {str(part.partname) for part in package.iter_parts()}
        number = 1
        while f"/customXml/item{number}.xml" in existing:
            number += 1
        item = Part(PackURI(f"/customXml/item{number}.xml"), "application/xml", blob, package)
        # The item id only has to be a GUID that is unique inside the package; a fixed one keeps builds repeatable.
        props_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
                     '<ds:datastoreItem ds:itemID="{8C5C0E4F-5E0B-4A0B-9C1D-5ED0C5A1D0C5}" '
                     'xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml">'
                     f'<ds:schemaRefs><ds:schemaRef ds:uri="{citations.B_NS}"/></ds:schemaRefs></ds:datastoreItem>')
        props = Part(PackURI(f"/customXml/itemProps{number}.xml"),
                     "application/vnd.openxmlformats-officedocument.customXmlProperties+xml",
                     props_xml.encode("utf-8"), package)
        item.relate_to(props, RT.CUSTOM_XML_PROPS)
        self.doc.part.relate_to(item, RT.CUSTOM_XML)

    # ------------------------------------------------------------------ templates
    def _all_paragraphs(self):
        yield from self.body.iter(qn("w:p"))
        for section in self.doc.sections:
            for part in (section.header, section.footer, section.first_page_header, section.first_page_footer):
                yield from part._element.iter(qn("w:p"))

    def _fill_placeholders(self) -> None:
        """Replace {{title}}, {{responsible}}, {{date}}... in the body, the headers and the footers."""
        values = {"{{" + key + "}}": self.meta[key] for key in PLACEHOLDERS}
        for paragraph in self._all_paragraphs():
            texts = paragraph.findall(".//" + qn("w:t"))
            joined = "".join(t.text or "" for t in texts)
            if "{{" not in joined or not any(key in joined for key in values):
                continue
            for key, replacement in values.items():
                joined = joined.replace(key, replacement)
            texts[0].text = joined          # a placeholder may be split across runs: keep the first one
            texts[0].set(qn("xml:space"), "preserve")
            for extra in texts[1:]:
                extra.text = ""

    def _move_to_marker(self, first_new: int) -> None:
        """When the template has a content marker paragraph, the content goes where the marker is."""
        marker_text = str(self.profile["content_marker"] or "")
        children = list(self.body)
        added = [el for el in children[first_new:] if el.tag != qn("w:sectPr")]
        marker = next((el for el in children[:first_new] if el.tag == qn("w:p")
                       and "".join(t.text or "" for t in el.iter(qn("w:t"))).strip() == marker_text), None)
        if marker is None or not marker_text:
            return
        anchor = marker
        for element in added:
            anchor.addnext(element)
            anchor = element
        self.body.remove(marker)


def load_spec(path: str | Path) -> tuple[dict, Path]:
    path = Path(path)
    try:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BuildError(f"document spec not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise BuildError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(spec, dict):
        raise BuildError(f"{path} must contain a YAML mapping")
    unknown = set(spec) - {"document", "profile", "model", "sources", "sections"}
    if unknown:
        raise BuildError(f"{path}: unknown top-level key(s) {', '.join(sorted(unknown))}")
    return spec, path.resolve().parent


def build_document(spec_path: str | Path, output: str | Path | None = None) -> BuildReport:
    spec, base_dir = load_spec(spec_path)
    target = Path(output) if output else base_dir / "out" / (Path(spec_path).stem + ".docx")
    return _Builder(spec, base_dir, target.resolve()).build()
