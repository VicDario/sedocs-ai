"""UML use case diagrams, laid out automatically from the project model.

Layout: primary human actors stand on the left of the system boundary and secondary or system
actors on the right. Use cases that a left-hand actor starts go in the first column; supporting use
cases (included, extending or started from the right) go in the second. A specialised use case does
not repeat the actors it inherits from its parent. Positions can be overridden per element.
"""
from __future__ import annotations

import math

from . import i18n
from .model import Project
from .svg import (
    CHAR_W_BOLD, STROKE, arrow_hollow, arrow_open, clip_to_shape, fx, halo_rect, line_path,
    segment_hits_ellipse, svg_open, text_block, text_block_top,
    text_width, wrap_label,
)

ACTOR_HALF_H = 40
HEAD_R = 14
ARM_HALF = 20
LEG_HALF = 16
ACTOR_LABEL_SIZE = 18
ACTOR_LABEL_LH = 22
ACTOR_LABEL_GAP = 8
ACTOR_WRAP = 16
ACTOR_CLIP_MARGIN = 6

UC_FONT = 20
UC_LH = 24
UC_WRAP = 20
RX_MIN, RX_MAX = 105, 152
RY_MIN = 42

REL_LABEL_SIZE = 17
REL_COND_SIZE = 14
COND_WRAP = 22

MARGIN = 24
ROW_GAP = 34
COL_GAP = 200
BOUNDARY_LABEL_SIZE = 22
BOUNDARY_LABEL_LH = 26
BULGE_OUT = 42
BULGE_STEP = 16
PORT_STEP = 14
PORT_LIMIT = 0.8     # share of the vertical radius a connection point may use


class DiagramError(Exception):
    """The requested diagram cannot be built from the model."""


# ----------------------------------------------------------------------- selection
def select_use_cases(project: Project, module: str | None = None, ids: list[str] | None = None,
                     neighbors: bool = True) -> list[dict]:
    if ids:
        chosen = []
        for uc_id in dict.fromkeys(ids):          # an id given twice is drawn once
            uc = project.use_case(uc_id)
            if uc is None:
                raise DiagramError(f"use case '{uc_id}' is not defined in the model")
            chosen.append(uc)
    elif module is not None:
        if project.module(module) is None:
            raise DiagramError(f"module '{module}' is not defined in the model")
        chosen = project.use_cases_of(module)
    else:
        chosen = list(project.use_cases)
    if not chosen:
        raise DiagramError("no use cases to draw")
    if neighbors:
        present = {u["id"] for u in chosen}
        for uc in list(chosen):
            targets = uc["includes"] + [e["target"] for e in uc["extends"]] + ([uc["specializes"]] if uc["specializes"] else [])
            for target in targets:
                other = project.use_case(target)
                if other is not None and target not in present:
                    chosen.append(other)
                    present.add(target)
    return chosen


# ----------------------------------------------------------------------- layout
def _uc_size(label: str) -> tuple[list[str], float, float]:
    lines = wrap_label(label, UC_WRAP)
    widest = max(text_width(line, UC_FONT) for line in lines)
    ry = max(RY_MIN, len(lines) * UC_LH / 2 + 22)
    rx = min(RX_MAX, max(RX_MIN, widest / 2 / 0.78 + 8))
    return lines, rx, ry


def _actor_lines(actor: dict, lang: str) -> list[str]:
    lines = wrap_label(actor["name"], ACTOR_WRAP)
    return ([i18n.t(lang, "system_stereotype")] if actor["kind"] == "system" else []) + lines


def _spread(targets: list[float], spacing: float, floor: float) -> list[float]:
    """Positions as close as possible to the targets (given in ascending order), at least
    `spacing` apart and never above `floor`."""
    placed: list[float] = []
    for target in targets:
        placed.append(max(target, floor if not placed else placed[-1] + spacing))
    if placed:
        drift = sum(t - p for t, p in zip(targets, placed)) / len(placed)  # <= 0
        shift = max(drift, floor - placed[0])
        placed = [p + shift for p in placed]
    return placed


def build_layout(project: Project, *, module: str | None = None, use_cases: list[str] | None = None,
                 title: str | None = None, positions: dict | None = None, neighbors: bool = True,
                 show_ids: bool = False) -> dict:
    lang = project.language
    chosen = select_use_cases(project, module, use_cases, neighbors)
    present = {u["id"] for u in chosen}
    order = {u["id"]: i for i, u in enumerate(chosen)}

    # Associations: a specialised use case inherits the actors of its parent.
    assoc: dict[str, list[str]] = {}
    for uc in chosen:
        actors = [a for a in uc["actors"] if project.actor(a) is not None]
        parent = project.use_case(uc["specializes"]) if uc["specializes"] in present else None
        if parent is not None:
            actors = [a for a in actors if a not in parent["actors"]]
        assoc[uc["id"]] = actors
    used = [a for a in project.actors if any(a["id"] in ids for ids in assoc.values())]
    right_ids = {a["id"] for a in used if a["kind"] == "system" or a["type"] in ("secondary", "external")}
    if len(right_ids) == len(used):
        right_ids = set()
    left = [a for a in used if a["id"] not in right_ids]
    right = [a for a in used if a["id"] in right_ids]
    left_rank = {a["id"]: i for i, a in enumerate(left)}

    col_a = [u for u in chosen if any(a in left_rank for a in assoc[u["id"]])]
    col_b = [u for u in chosen if u not in col_a]
    if not col_a:
        col_a, col_b = col_b, []
    col_a.sort(key=lambda u: (min((left_rank[a] for a in assoc[u["id"]] if a in left_rank), default=0), order[u["id"]]))

    sizes = {u["id"]: _uc_size((u["id"] + "\n" if show_ids else "") + u["name"]) for u in chosen}
    rx = max(size[1] for size in sizes.values())
    ry_max = max(size[2] for size in sizes.values())
    row_h = 2 * ry_max + ROW_GAP

    # Relations between use cases, kept in model order.
    relations: list[dict] = []
    for uc in chosen:
        for target in uc["includes"]:
            if target in present:
                relations.append({"type": "include", "from": uc["id"], "to": target, "condition": ""})
        for ext in uc["extends"]:
            if ext["target"] in present:
                relations.append({"type": "extend", "from": uc["id"], "to": ext["target"], "condition": ext["condition"]})
        if uc["specializes"] in present:
            relations.append({"type": "generalization", "from": uc["id"], "to": uc["specializes"], "condition": ""})

    y: dict[str, float] = {u["id"]: i * row_h for i, u in enumerate(col_a)}
    if col_b:
        linked: dict[str, list[str]] = {u["id"]: [] for u in col_b}
        for rel in relations:
            for a, b in ((rel["from"], rel["to"]), (rel["to"], rel["from"])):
                if a in linked:
                    linked[a].append(b)
        bary: dict[str, float] = {}
        for uc in col_b:
            anchors = [y[o] for o in linked[uc["id"]] if o in y]
            if anchors:
                bary[uc["id"]] = sum(anchors) / len(anchors)
        for uc in col_b:  # no link to the first column: follow a linked neighbour, else keep model order
            if uc["id"] not in bary:
                anchors = [bary[o] for o in linked[uc["id"]] if o in bary]
                bary[uc["id"]] = sum(anchors) / len(anchors) if anchors else order[uc["id"]] * row_h
        col_b.sort(key=lambda u: (bary[u["id"]], order[u["id"]]))
        for uc, pos in zip(col_b, _spread([bary[u["id"]] for u in col_b], row_h, 0.0)):
            y[uc["id"]] = pos

    # Same-column relations leave by the right side of the column and come back in.
    column = {u["id"]: 0 for u in col_a} | {u["id"]: 1 for u in col_b}
    bulges = {0: 0, 1: 0}
    label_room = {0: 0.0, 1: 0.0}
    ports: dict[str, int] = {}
    for rel in relations:
        if column[rel["from"]] == column[rel["to"]]:
            col = column[rel["from"]]
            rel["bulge"] = bulges[col]
            bulges[col] += 1
            label_room[col] = max(label_room[col], _relation_label_width(rel) + 16)
            for end in ("from", "to"):  # 0, +14, -14, +28, ... around the middle of the ellipse
                n = ports.get(rel[end], 0)
                ports[rel[end]] = n + 1
                reach = PORT_LIMIT * sizes[rel[end]][2]     # past this the line would miss the outline
                offset = ((n + 1) // 2) * PORT_STEP * (1 if n % 2 else -1) if n else 0
                rel[end + "_dy"] = max(-reach, min(reach, offset))
    gap = max(COL_GAP, BULGE_OUT + bulges[0] * BULGE_STEP + label_room[0] + 30) if col_b else 0
    last = 1 if col_b else 0
    right_pad = max(60, BULGE_OUT + bulges[last] * BULGE_STEP + label_room[last] + 20)

    x: dict[str, float] = {}
    for uc in col_a:
        x[uc["id"]] = 0.0
    for uc in col_b:
        x[uc["id"]] = 2 * rx + gap

    usecases = [{"id": u["id"], "lines": sizes[u["id"]][0], "x": x[u["id"]], "y": y[u["id"]],
                 "rx": rx, "ry": sizes[u["id"]][2]} for u in chosen]

    def actor_entries(group: list[dict], side: str) -> list[dict]:
        entries = []
        for actor in group:
            ys = [y[uid] for uid, ids in assoc.items() if actor["id"] in ids]
            entries.append({"id": actor["id"], "kind": actor["kind"], "side": side,
                            "lines": _actor_lines(actor, lang), "target": sum(ys) / len(ys)})
        entries.sort(key=lambda e: e["target"])
        tallest = max((len(e["lines"]) for e in entries), default=1)
        spacing = 2 * ACTOR_HALF_H + ACTOR_LABEL_GAP + tallest * ACTOR_LABEL_LH + 34
        for entry, pos in zip(entries, _spread([e["target"] for e in entries], spacing, 0.0)):
            entry["y"] = pos
        return entries

    actors = actor_entries(left, "left") + actor_entries(right, "right")
    for entry in actors:
        half = max(ARM_HALF, max(text_width(line, ACTOR_LABEL_SIZE) for line in entry["lines"]) / 2)
        entry["half_w"] = half
        entry["x"] = (-rx - 60 - 60 - half) if entry["side"] == "left" else (max(x.values()) + rx + right_pad + 60 + half)

    label = title or (f"{project.name}: {project.module(module)['name']}" if module and project.module(module) else project.name)
    spec = {
        "language": lang, "label": label, "usecases": usecases, "actors": actors, "relations": relations,
        "associations": [{"actor": a, "usecase": uid} for uid, ids in assoc.items() for a in ids],
        "right_pad": right_pad,
    }
    _finalize(spec)
    if positions:  # manual overrides, in the coordinates of the drawing produced without them
        unknown = sorted(set(positions) - {e["id"] for e in usecases + actors})
        if unknown:
            raise DiagramError(f"positions given for elements that are not in the diagram: {', '.join(unknown)}")
        for element in usecases + actors:
            if element["id"] in positions:
                try:
                    px, py = positions[element["id"]]
                    element["x"], element["y"] = float(px), float(py)
                except (TypeError, ValueError):
                    raise DiagramError(f"positions: '{element['id']}' needs two numbers [x, y], "
                                       f"found {positions[element['id']]!r}") from None
        _finalize(spec, keep=True)
    return spec


def _relation_label_lines(rel: dict) -> list[tuple[str, float]]:
    if rel["type"] == "generalization":
        return []
    lines = [("«include»" if rel["type"] == "include" else "«extend»", REL_LABEL_SIZE)]
    if rel["condition"]:
        lines += [(line, REL_COND_SIZE) for line in wrap_label("{" + rel["condition"] + "}", COND_WRAP)]
    return lines


def _relation_label_width(rel: dict) -> float:
    return max((text_width(text, size) for text, size in _relation_label_lines(rel)), default=0.0)


def _actor_bottom(actor: dict) -> float:
    return actor["y"] + ACTOR_HALF_H + ACTOR_LABEL_GAP + len(actor["lines"]) * ACTOR_LABEL_LH


def _finalize(spec: dict, keep: bool = False) -> None:
    """Place the system boundary around the use cases and fit the canvas to everything.

    With keep=True the elements stay where they are (manual positions) unless one of them would
    fall off the top or the left of the canvas.
    """
    usecases, actors = spec["usecases"], spec["actors"]
    x0 = min(u["x"] - u["rx"] for u in usecases) - 60
    x1 = max(u["x"] + u["rx"] for u in usecases) + spec["right_pad"]
    label_lines = wrap_label(spec["label"], max(10, int((x1 - x0 - 24) / (BOUNDARY_LABEL_SIZE * CHAR_W_BOLD))))
    label_h = 14 + len(label_lines) * BOUNDARY_LABEL_LH
    y0 = min(u["y"] - u["ry"] for u in usecases) - label_h - 22
    y1 = max(u["y"] + u["ry"] for u in usecases) + 40

    min_x = min([x0] + [a["x"] - a["half_w"] for a in actors])
    min_y = min([y0] + [a["y"] - ACTOR_HALF_H for a in actors])
    dx = 0.0 if keep and min_x >= 0 else MARGIN - min_x
    dy = 0.0 if keep and min_y >= 0 else MARGIN - min_y
    for element in usecases + actors:
        element["x"] += dx
        element["y"] += dy
    x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
    spec["boundary"] = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "lines": label_lines}
    spec["width"] = max([x1] + [a["x"] + a["half_w"] for a in actors]) + MARGIN
    spec["height"] = max([y1] + [_actor_bottom(a) for a in actors]) + MARGIN


# ----------------------------------------------------------------------- geometry
def _shapes(spec: dict) -> dict[str, dict]:
    shapes: dict[str, dict] = {}
    for uc in spec["usecases"]:
        shapes[uc["id"]] = {"kind": "ellipse", "center": (uc["x"], uc["y"]), "rx": uc["rx"], "ry": uc["ry"]}
    for actor in spec["actors"]:
        m = ACTOR_CLIP_MARGIN
        shapes["actor:" + actor["id"]] = {
            "kind": "rect", "center": (actor["x"], actor["y"]),
            "bounds": (actor["x"] - actor["half_w"] - m, actor["y"] - ACTOR_HALF_H - m,
                       actor["x"] + actor["half_w"] + m, _actor_bottom(actor) + m),
        }
    return shapes


def _right_edge(shape: dict, dy: float) -> tuple[float, float]:
    """Point of the ellipse outline at height dy from its centre, on the right side."""
    cx, cy = shape["center"]
    return (cx + shape["rx"] * math.sqrt(max(0.0, 1 - (dy / shape["ry"]) ** 2)), cy + dy)


def _relation_points(rel: dict, shapes: dict) -> list[tuple[float, float]]:
    src, dst = shapes[rel["from"]], shapes[rel["to"]]
    if "bulge" in rel:  # out by the right side, along the column, and back in
        out = max(src["center"][0] + src["rx"], dst["center"][0] + dst["rx"]) + BULGE_OUT + rel["bulge"] * BULGE_STEP
        start, end = _right_edge(src, rel.get("from_dy", 0)), _right_edge(dst, rel.get("to_dy", 0))
        return [start, (out, start[1]), (out, end[1]), end]
    return [clip_to_shape(src, dst["center"]), clip_to_shape(dst, src["center"])]


def _association_points(link: dict, shapes: dict) -> list[tuple[float, float]]:
    src, dst = shapes["actor:" + link["actor"]], shapes[link["usecase"]]
    return [clip_to_shape(src, dst["center"]), clip_to_shape(dst, src["center"])]


def find_crossings(spec: dict) -> list[str]:
    """Lines that pass through a use case they do not connect. Fix them with position overrides."""
    shapes = _shapes(spec)
    lines = [(f"{rel['type']} {rel['from']} → {rel['to']}", _relation_points(rel, shapes), {rel["from"], rel["to"]})
             for rel in spec["relations"]]
    lines += [(f"association {link['actor']} – {link['usecase']}", _association_points(link, shapes), {link["usecase"]})
              for link in spec["associations"]]
    found = []
    for name, points, own in lines:
        for uc in spec["usecases"]:
            if uc["id"] in own:
                continue
            if any(segment_hits_ellipse(p0, p1, (uc["x"], uc["y"]), uc["rx"], uc["ry"]) for p0, p1 in zip(points, points[1:])):
                found.append(f"{name} crosses use case {uc['id']}")
    return found


# ----------------------------------------------------------------------- drawing
def _draw_actor(actor: dict) -> str:
    x, y = actor["x"], actor["y"]
    top, feet = y - ACTOR_HALF_H, y + ACTOR_HALF_H
    neck, hip = top + 2 * HEAD_R, y + 14
    s = f'stroke="{STROKE}" stroke-width="2" stroke-linecap="round"'
    return "\n".join([
        f'<circle cx="{fx(x)}" cy="{fx(top + HEAD_R)}" r="{HEAD_R}" fill="white" {s}/>',
        f'<line x1="{fx(x)}" y1="{fx(neck)}" x2="{fx(x)}" y2="{fx(hip)}" {s}/>',
        f'<line x1="{fx(x - ARM_HALF)}" y1="{fx(neck + 12)}" x2="{fx(x + ARM_HALF)}" y2="{fx(neck + 12)}" {s}/>',
        f'<line x1="{fx(x)}" y1="{fx(hip)}" x2="{fx(x - LEG_HALF)}" y2="{fx(feet)}" {s}/>',
        f'<line x1="{fx(x)}" y1="{fx(hip)}" x2="{fx(x + LEG_HALF)}" y2="{fx(feet)}" {s}/>',
        text_block_top(x, feet + ACTOR_LABEL_GAP, actor["lines"], ACTOR_LABEL_SIZE, anchor="middle",
                       line_height=ACTOR_LABEL_LH),
    ])


def _draw_usecase(uc: dict) -> str:
    return "\n".join([
        f'<ellipse cx="{fx(uc["x"])}" cy="{fx(uc["y"])}" rx="{fx(uc["rx"])}" ry="{fx(uc["ry"])}" '
        f'fill="white" stroke="{STROKE}" stroke-width="2"/>',
        text_block(uc["x"], uc["y"], uc["lines"], UC_FONT, line_height=UC_LH),
    ])


def _segment_hits_box(p0, p1, box) -> bool:
    """True when the segment touches the axis-aligned box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, p0[0] - x0), (dx, x1 - p0[0]), (-dy, p0[1] - y0), (dy, y1 - p0[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
    return t0 <= t1


def _boxes_overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _place_labels(spec: dict, shapes: dict) -> dict[int, tuple[float, float]]:
    """Centre of the label of each include/extend relation, chosen among a few spots along the
    line as the one that covers the fewest other lines, labels and shapes."""
    lines = {i: _relation_points(rel, shapes) for i, rel in enumerate(spec["relations"])}
    other_lines = [_association_points(link, shapes) for link in spec["associations"]]
    obstacles = [(u["x"] - u["rx"], u["y"] - u["ry"], u["x"] + u["rx"], u["y"] + u["ry"]) for u in spec["usecases"]]
    obstacles += [shapes["actor:" + a["id"]]["bounds"] for a in spec["actors"]]
    placed: dict[int, tuple[float, float]] = {}
    boxes: list[tuple[float, float, float, float]] = []
    for i, rel in enumerate(spec["relations"]):
        label = _relation_label_lines(rel)
        if not label:
            continue
        width = max(text_width(text, size) for text, size in label) + 8
        height = sum(size * 1.25 for _, size in label) + 6
        points = lines[i]
        if "bulge" in rel:
            (ax, ay), (bx, by) = points[1], points[2]
            candidates = [(ax + 10 + width / 2, ay + (by - ay) * f) for f in (0.5, 0.25, 0.75, 0.12, 0.88)]
        else:
            (ax, ay), (bx, by) = points[0], points[-1]
            candidates = [(ax + (bx - ax) * f, ay + (by - ay) * f) for f in (0.5, 0.36, 0.64, 0.24, 0.76)]
        best, best_cost = candidates[0], None
        for cx, cy in candidates:
            box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
            cost = 3 * sum(_boxes_overlap(box, other) for other in boxes + obstacles)
            for j, other in lines.items():
                if j != i:
                    cost += sum(_segment_hits_box(p0, p1, box) for p0, p1 in zip(other, other[1:]))
            cost += sum(_segment_hits_box(line[0], line[1], box) for line in other_lines)
            if best_cost is None or cost < best_cost:
                best, best_cost = (cx, cy), cost
        placed[i] = best
        boxes.append((best[0] - width / 2, best[1] - height / 2, best[0] + width / 2, best[1] + height / 2))
    return placed


def _draw_relation(rel: dict, shapes: dict, label_at: tuple[float, float] | None) -> str:
    points = _relation_points(rel, shapes)
    tip, prev = points[-1], points[-2]
    if rel["type"] == "generalization":
        head, base = arrow_hollow(tip, prev)
        return "\n".join([line_path(points[:-1] + [base]), head])
    parts = [line_path(points, dashed=True), arrow_open(tip, prev)]
    lines = _relation_label_lines(rel)
    mx, my = label_at
    heights = [size * 1.25 for _, size in lines]
    parts.append(halo_rect(mx, my, lines, line_height=sum(heights) / len(heights)))
    cursor = my - sum(heights) / 2
    for (text, size), height in zip(lines, heights):
        parts.append(text_block(mx, cursor + height / 2, [text], size))
        cursor += height
    return "\n".join(parts)


def render(spec: dict) -> str:
    out = svg_open(spec["width"], spec["height"])
    b = spec["boundary"]
    out.append(f'<rect x="{fx(b["x"])}" y="{fx(b["y"])}" width="{fx(b["w"])}" height="{fx(b["h"])}" '
               f'fill="none" stroke="{STROKE}" stroke-width="2"/>')
    out.append(text_block_top(b["x"] + b["w"] / 2, b["y"] + 12, b["lines"], BOUNDARY_LABEL_SIZE, anchor="middle",
                              line_height=BOUNDARY_LABEL_LH, bold=True))
    shapes = _shapes(spec)
    for link in spec["associations"]:
        out.append(line_path(_association_points(link, shapes)))
    labels = _place_labels(spec, shapes)
    for i, rel in enumerate(spec["relations"]):
        out.append(_draw_relation(rel, shapes, labels.get(i)))
    for uc in spec["usecases"]:
        out.append(_draw_usecase(uc))
    for actor in spec["actors"]:
        out.append(_draw_actor(actor))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_use_case_diagram(project: Project, **options) -> tuple[str, list[str]]:
    """SVG of a use case diagram and the list of layout warnings (lines crossing use cases)."""
    spec = build_layout(project, **options)
    return render(spec), find_crossings(spec)
