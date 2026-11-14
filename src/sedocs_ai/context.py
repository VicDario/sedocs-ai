"""Context diagram: the system as one bubble and the actors around it with their data flows.

Flows come from `context.flows` in the project model. Each actor gets at most two arrows: what it
sends to the system (direction: in) and what it receives from it (direction: out).
"""
from __future__ import annotations

import math

from . import i18n
from .model import Project
from .svg import CHAR_W_BOLD, CHAR_W_WRAP, STROKE, arrow_filled, fx, line_path, svg_open, text_block, wrap_label
from .usecase import DiagramError

ENTITY_W, ENTITY_H = 230, 86
ENTITY_FONT = 20
SYSTEM_RX = 150
SYSTEM_FONT = 22
FLOW_FONT = 16
FLOW_LH = 20
FLOW_WRAP = 30
FLOW_GAP = 320      # room between an entity and the system bubble for the flow labels
ROW_H = 180
MARGIN = 24
OFFSET = 13         # half the distance between the two arrows of one actor


def build_layout(project: Project, title: str | None = None) -> dict:
    lang = project.language
    flows: dict[str, dict[str, list[str]]] = {}
    for flow in project.context_flows:
        actor, direction, label = str(flow.get("actor")), flow.get("direction"), str(flow.get("label") or "").strip()
        if project.actor(actor) is None or direction not in ("in", "out") or not label:
            raise DiagramError(f"context flow {dict(flow)!r} needs a defined actor, direction 'in' or 'out' and a label; "
                               "run 'sedocs check' on the model")
        flows.setdefault(actor, {"in": [], "out": []})[direction].append(label)
    actors = [a for a in project.actors if a["id"] in flows]
    if not actors:
        raise DiagramError("the model has no context flows: add 'context.flows' entries with actor, direction and label")

    right = [a for a in actors if a["kind"] == "system" or a["type"] in ("secondary", "external")]
    left = [a for a in actors if a not in right]
    while len(left) - len(right) > 1:      # keep both sides balanced
        right.insert(0, left.pop())
    while len(right) - len(left) > 1:
        left.append(right.pop(0))

    rows = max(len(left), len(right))
    ry = max(SYSTEM_RX, rows * ROW_H / 2)   # the bubble grows with the number of rows it serves
    height = 2 * ry + 2 * MARGIN
    left_x = MARGIN + ENTITY_W / 2
    cx = (left_x + ENTITY_W / 2 + FLOW_GAP + SYSTEM_RX) if left else MARGIN + SYSTEM_RX
    right_x = cx + SYSTEM_RX + FLOW_GAP + ENTITY_W / 2
    width = (right_x + ENTITY_W / 2 + MARGIN) if right else cx + SYSTEM_RX + MARGIN
    cy = height / 2

    entities = []
    for group, x in ((left, left_x), (right, right_x)):
        for i, actor in enumerate(group):
            y = cy + (i - (len(group) - 1) / 2) * ROW_H
            lines = wrap_label(actor["name"], max(6, int((ENTITY_W - 16) / (ENTITY_FONT * CHAR_W_WRAP))))
            if actor["kind"] == "system":
                lines = [i18n.t(lang, "system_stereotype")] + lines
            entities.append({"id": actor["id"], "x": x, "y": y, "lines": lines,
                             "in": "; ".join(flows[actor["id"]]["in"]), "out": "; ".join(flows[actor["id"]]["out"])})
    return {"width": width, "height": height, "entities": entities,
            "system": {"x": cx, "y": cy, "rx": SYSTEM_RX, "ry": ry, "label": title or project.name}}


def _edge_x(system: dict, y: float, side: int) -> float:
    """x of the system outline at height y, on the left (-1) or the right (+1) side."""
    dy = min(abs(y - system["y"]) / system["ry"], 0.98)
    return system["x"] + side * system["rx"] * math.sqrt(1 - dy * dy)


def render(spec: dict) -> str:
    out = svg_open(spec["width"], spec["height"])
    system = spec["system"]
    for ent in spec["entities"]:
        side = -1 if ent["x"] < system["x"] else 1          # which side of the system the entity is on
        entity_x = ent["x"] - side * ENTITY_W / 2
        # Two horizontal arrows: towards the system above, from the system below.
        for label, dy, inbound in ((ent["in"], -OFFSET, True), (ent["out"], OFFSET, False)):
            if not label:
                continue
            y = ent["y"] + dy
            system_x = _edge_x(system, y, side)
            p0, p1 = ((entity_x, y), (system_x, y)) if inbound else ((system_x, y), (entity_x, y))
            head, base = arrow_filled(p1, p0)
            out.append(line_path([p0, base]))
            out.append(head)
            lines = wrap_label(label, FLOW_WRAP)
            ly = y + (-1 if inbound else 1) * (10 + len(lines) * FLOW_LH / 2)
            out.append(text_block((entity_x + system_x) / 2, ly, lines, FLOW_FONT, line_height=FLOW_LH))

    out.append(f'<ellipse cx="{fx(system["x"])}" cy="{fx(system["y"])}" rx="{fx(system["rx"])}" ry="{fx(system["ry"])}" '
               f'fill="white" stroke="{STROKE}" stroke-width="3"/>')
    label = wrap_label(system["label"], max(8, int((2 * system["rx"] * 0.8) / (SYSTEM_FONT * CHAR_W_BOLD))))
    out.append(text_block(system["x"], system["y"], label, SYSTEM_FONT, bold=True, line_height=28))
    for ent in spec["entities"]:
        out.append(f'<rect x="{fx(ent["x"] - ENTITY_W / 2)}" y="{fx(ent["y"] - ENTITY_H / 2)}" width="{ENTITY_W}" '
                   f'height="{ENTITY_H}" fill="white" stroke="{STROKE}" stroke-width="2"/>')
        out.append(text_block(ent["x"], ent["y"], ent["lines"], ENTITY_FONT, line_height=24))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_context_diagram(project: Project, title: str | None = None) -> str:
    return render(build_layout(project, title))
