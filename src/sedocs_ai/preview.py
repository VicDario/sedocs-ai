"""Render a Word document to PDF and to page images, so a person or an agent can look at it."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PreviewError(RuntimeError):
    pass


def _office() -> str:
    for name in ("soffice", "libreoffice"):
        if shutil.which(name):
            return name
    raise PreviewError("LibreOffice is not installed: it is needed to turn the .docx into a PDF")


def docx_to_pdf(docx_path: str | Path, out_dir: str | Path) -> Path:
    docx_path, out_dir = Path(docx_path).resolve(), Path(out_dir).resolve()
    if not docx_path.is_file():
        raise PreviewError(f"file not found: {docx_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / (docx_path.stem + ".pdf")
    pdf.unlink(missing_ok=True)          # a PDF from an earlier run must not pass for this one
    try:
        result = subprocess.run([_office(), "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
                                capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise PreviewError("LibreOffice did not finish converting the document within 5 minutes") from exc
    if result.returncode != 0 or not pdf.is_file():
        raise PreviewError("LibreOffice did not produce a PDF: " + (result.stderr.strip() or result.stdout.strip()))
    return pdf


def pdf_to_pngs(pdf: Path, out_dir: Path, dpi: int = 80) -> list[Path]:
    if not shutil.which("pdftoppm"):
        raise PreviewError("pdftoppm (poppler) is not installed: it is needed to turn the PDF pages into images")
    prefix = out_dir / (pdf.stem + "-page")
    for old in out_dir.glob(prefix.name + "-*.png"):
        old.unlink()
    try:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)], check=True, capture_output=True,
                       text=True, timeout=300)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PreviewError(f"pdftoppm could not render {pdf.name}: {(getattr(exc, 'stderr', '') or '').strip()}") from exc
    return sorted(out_dir.glob(prefix.name + "-*.png"))


def preview(docx_path: str | Path, out_dir: str | Path | None = None, dpi: int = 80, images: bool = True):
    """PDF of the document and one PNG per page. Pagination is LibreOffice's, close to Word's."""
    docx_path = Path(docx_path)
    out_dir = Path(out_dir) if out_dir else docx_path.resolve().parent / ".sedocs" / "preview"
    pdf = docx_to_pdf(docx_path, out_dir)
    return pdf, (pdf_to_pngs(pdf, out_dir, dpi) if images else [])
