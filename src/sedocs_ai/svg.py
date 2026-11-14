"""Standard-library SVG primitives shared by the diagram renderers.

Everything is drawn in dark gray on white. Geometry helpers clip line endpoints to the shapes they
connect (ellipse, circle, rectangle), so lines never poke into a shape.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape as _xml_escape

FONT_FAMILY = "Liberation Sans, Arial, Helvetica, sans-serif"
STROKE = "#333"

# Average glyph advance as a fraction of the font size. CHAR_W is a bit generous because it sizes
# boxes and halos; CHAR_W_WRAP is tighter and only decides when a wrap is really needed.
CHAR_W = 0.54
CHAR_W_BOLD = 0.58
CHAR_W_WRAP = 0.50

OPEN_ARROW = 14
HOLLOW_ARROW = 16
FILLED_ARROW = 12


def esc(text) -> str:
    return _xml_escape(str(text), {'"': "&quot;"})


def fx(value) -> str:
    """Format a number compactly for SVG attributes."""
    s = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def wrap_label(text: str, max_chars: int) -> list[str]:
    """Greedy word wrap. Explicit newlines always start a new line."""
    max_chars = max(1, int(max_chars))
    lines: list[str] = []
    for raw in str(text).split("\n"):
        words = raw.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= max_chars:
                current += " " + word
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def text_width(text: str, size: float, bold: bool = False) -> float:
    return len(text) * size * (CHAR_W_BOLD if bold else CHAR_W)


def unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    return (1.0, 0.0) if length == 0 else (dx / length, dy / length)


def _rotate(ux: float, uy: float, angle: float) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return (ux * c - uy * s, ux * s + uy * c)


# ----------------------------------------------------------------------- clipping
def clip_ellipse(center, toward, rx, ry):
    cx, cy = center
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return (cx, cy)
    t = 1.0 / math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
    return (cx + dx * t, cy + dy * t)


def clip_circle(center, toward, r):
    cx, cy = center
    ux, uy = unit(toward[0] - cx, toward[1] - cy)
    return (cx + ux * r, cy + uy * r)


def clip_rect(center, toward, x0, y0, x1, y1):
    cx, cy = center
    dx, dy = toward[0] - cx, toward[1] - cy
    ts = []
    if dx > 0:
        ts.append((x1 - cx) / dx)
    elif dx < 0:
        ts.append((x0 - cx) / dx)
    if dy > 0:
        ts.append((y1 - cy) / dy)
    elif dy < 0:
        ts.append((y0 - cy) / dy)
    if not ts:
        return (cx, cy)
    t = min(ts)
    return (cx + dx * t, cy + dy * t)


def clip_to_shape(shape: dict, toward) -> tuple[float, float]:
    kind = shape["kind"]
    if kind == "ellipse":
        return clip_ellipse(shape["center"], toward, shape["rx"], shape["ry"])
    if kind == "circle":
        return clip_circle(shape["center"], toward, shape["r"])
    if kind == "rect":
        return clip_rect(shape["center"], toward, *shape["bounds"])
    raise ValueError(f"unknown shape kind: {kind}")


def segment_hits_ellipse(p0, p1, center, rx, ry, shrink: float = 0.94) -> bool:
    """True when the segment p0-p1 passes through the ellipse (slightly shrunk to ignore grazes)."""
    ax, ay = (p0[0] - center[0]) / (rx * shrink), (p0[1] - center[1]) / (ry * shrink)
    bx, by = (p1[0] - center[0]) / (rx * shrink), (p1[1] - center[1]) / (ry * shrink)
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return ax * ax + ay * ay < 1
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    px, py = ax + t * dx, ay + t * dy
    return px * px + py * py < 1


# ----------------------------------------------------------------------- drawing
def svg_open(width, height) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fx(width)}" height="{fx(height)}" '
        f'viewBox="0 0 {fx(width)} {fx(height)}" font-family="{FONT_FAMILY}" fill="{STROKE}">',
        f'<rect x="0" y="0" width="{fx(width)}" height="{fx(height)}" fill="white"/>',
    ]


def text_block(x, y, lines, size, *, anchor="middle", bold=False, line_height=None, italic=False) -> str:
    """Multi-line text whose block is vertically centered on y."""
    lh = line_height if line_height is not None else round(size * 1.2)
    first = y - (len(lines) - 1) * lh / 2 + size * 0.35
    attrs = f'x="{fx(x)}" y="{fx(first)}" font-size="{fx(size)}" text-anchor="{anchor}"'
    if bold:
        attrs += ' font-weight="bold"'
    if italic:
        attrs += ' font-style="italic"'
    parts = [f"<text {attrs}>"]
    for i, line in enumerate(lines):
        parts.append(f'<tspan x="{fx(x)}" dy="{fx(0 if i == 0 else lh)}">{esc(line)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def text_block_top(x, y_top, lines, size, *, anchor="start", line_height=None, bold=False) -> str:
    """Multi-line text whose first line starts at y_top."""
    lh = line_height if line_height is not None else round(size * 1.25)
    return text_block(x, y_top + (len(lines) * lh) / 2, lines, size, anchor=anchor, line_height=lh, bold=bold)


def halo_rect(x, y, lines_with_sizes, pad=4, line_height=None) -> str:
    """White rectangle that covers a text block centered on (x, y), so lines do not cross labels."""
    w = max(text_width(t, s) for t, s in lines_with_sizes) + 2 * pad
    lh = line_height if line_height is not None else max(s for _, s in lines_with_sizes) * 1.2
    h = len(lines_with_sizes) * lh + pad
    return (f'<rect x="{fx(x - w / 2)}" y="{fx(y - h / 2)}" width="{fx(w)}" height="{fx(h)}" '
            f'fill="white" opacity="0.92"/>')


def line_path(points, dashed=False, width=2) -> str:
    d = " ".join(f"{fx(px)},{fx(py)}" for px, py in points)
    dash = ' stroke-dasharray="9 6"' if dashed else ""
    return (f'<polyline points="{d}" fill="none" stroke="{STROKE}" stroke-width="{width}" '
            f'stroke-linejoin="round"{dash}/>')


def arrow_open(tip, prev, size=OPEN_ARROW, angle_deg=28) -> str:
    ux, uy = unit(tip[0] - prev[0], tip[1] - prev[1])
    a = math.radians(angle_deg)
    p1 = _rotate(-ux, -uy, a)
    p2 = _rotate(-ux, -uy, -a)
    pts = [(tip[0] + p1[0] * size, tip[1] + p1[1] * size), tip, (tip[0] + p2[0] * size, tip[1] + p2[1] * size)]
    d = " ".join(f"{fx(px)},{fx(py)}" for px, py in pts)
    return (f'<polyline points="{d}" fill="none" stroke="{STROKE}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def _triangle(tip, prev, size, half_ratio):
    ux, uy = unit(tip[0] - prev[0], tip[1] - prev[1])
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    half = size * half_ratio
    return [tip, (bx - uy * half, by + ux * half), (bx + uy * half, by - ux * half)], (bx, by)


def arrow_hollow(tip, prev, size=HOLLOW_ARROW):
    """Returns (svg, base_point); the connecting line should end at base_point."""
    pts, base = _triangle(tip, prev, size, 0.55)
    d = " ".join(f"{fx(px)},{fx(py)}" for px, py in pts)
    return f'<polygon points="{d}" fill="white" stroke="{STROKE}" stroke-width="2" stroke-linejoin="miter"/>', base


def arrow_filled(tip, prev, size=FILLED_ARROW):
    pts, base = _triangle(tip, prev, size, 0.45)
    d = " ".join(f"{fx(px)},{fx(py)}" for px, py in pts)
    return f'<polygon points="{d}" fill="{STROKE}" stroke="{STROKE}" stroke-width="1"/>', base


def longest_segment_midpoint(points):
    best, best_len = points[0], -1.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        if length > best_len:
            best_len, best = length, ((x0 + x1) / 2, (y0 + y1) / 2)
    return best
