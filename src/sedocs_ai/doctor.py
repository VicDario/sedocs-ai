"""Report which of the tools sedocs relies on are installed."""
from __future__ import annotations

import importlib
import shutil

PYTHON_MODULES = (("docx", "python-docx", "building Word documents"), ("yaml", "PyYAML", "reading models and specs"))
SVG_CONVERTERS = ("rsvg-convert", "inkscape", "magick")
EXTERNAL = (
    (("soffice", "libreoffice"), "LibreOffice", "PDF preview of documents (sedocs preview)"),
    (("pdftoppm",), "poppler-utils", "page images in the preview"),
)


def check() -> tuple[list[str], bool]:
    """Lines of the report and whether everything the core commands need is present."""
    lines, ok = [], True
    for module, package, purpose in PYTHON_MODULES:
        try:
            importlib.import_module(module)
            lines.append(f"ok       {package}: {purpose}")
        except ImportError:
            ok = False
            lines.append(f"MISSING  {package}: {purpose}; reinstall sedocs-ai")
    converter = next((tool for tool in SVG_CONVERTERS if shutil.which(tool)), None)
    if converter:
        lines.append(f"ok       {converter}: diagrams as PNG and inside documents")
    else:
        lines.append("missing  SVG converter (librsvg, Inkscape or ImageMagick): diagrams can only be written as "
                     ".svg and documents cannot embed them")
    for names, package, purpose in EXTERNAL:
        found = next((name for name in names if shutil.which(name)), None)
        lines.append(f"ok       {found}: {purpose}" if found else f"missing  {package}: {purpose}")
    return lines, ok
