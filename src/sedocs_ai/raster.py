"""SVG to PNG conversion with whichever converter is installed."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class RenderToolMissing(RuntimeError):
    pass


def svg_to_png(svg_path: str | Path, png_path: str | Path, width: int = 2400) -> Path:
    svg_path, png_path = Path(svg_path), Path(png_path)
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
    subprocess.run(command, check=True, capture_output=True)
    return png_path


def png_size(path: str | Path) -> tuple[int, int]:
    """Pixel size of a PNG, read from its header."""
    import struct

    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", head[16:24])
