"""SVG to PNG conversion with whichever converter is installed."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class RenderError(RuntimeError):
    """A diagram could not be turned into an image."""


class RenderToolMissing(RenderError):
    pass


def svg_to_png(svg_path: str | Path, png_path: str | Path, width: int = 2400) -> Path:
    # Absolute paths: a file name that starts with a dash is never read as an option.
    svg_path, png_path = Path(svg_path).resolve(), Path(png_path).resolve()
    if shutil.which("rsvg-convert"):
        command = ["rsvg-convert", "-w", str(width), str(svg_path), "-o", str(png_path)]
    elif shutil.which("inkscape"):
        command = ["inkscape", str(svg_path), "--export-type=png", f"--export-width={width}",
                   f"--export-filename={png_path}"]
    elif shutil.which("magick"):
        command = ["magick", "-background", "white", "-density", "300", str(svg_path), "-resize", f"{width}x", str(png_path)]
    else:
        raise RenderToolMissing(
            "no SVG converter found: install librsvg (rsvg-convert), Inkscape or ImageMagick, "
            "or ask for the .svg output instead")
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = (getattr(exc, "stderr", "") or "").strip().splitlines()[-1:] or ["no message"]
        raise RenderError(f"{command[0]} could not convert {svg_path.name}: {detail[0]}") from exc
    if not png_path.is_file():
        raise RenderError(f"{command[0]} could not convert {svg_path.name}: no image was written")
    return png_path


def png_size(path: str | Path) -> tuple[int, int]:
    """Pixel size of a PNG, read from its header."""
    import struct

    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", head[16:24])
