import copy
import itertools
import shutil
import xml.etree.ElementTree as ET

import pytest

from sedocs_ai.context import render_context_diagram
from sedocs_ai.model import Project
from sedocs_ai.raster import png_size, svg_to_png
from sedocs_ai.usecase import DiagramError, build_layout, find_crossings, render, render_use_case_diagram


def test_use_case_diagram_is_well_formed_and_complete(example_project):
    svg, warnings = render_use_case_diagram(example_project, module="M1")
    ET.fromstring(svg)  # raises if the SVG is not well-formed XML
    for text in ("Receptionist", "Pet owner", "«system»", "Send confirmation", "«include»", "«extend»"):
        assert text in svg
    assert "Appointment Booking System: Scheduling" in svg
    assert warnings == []


def test_layout_keeps_shapes_apart_and_inside_the_canvas(example_project):
    spec = build_layout(example_project)
    for a, b in itertools.combinations(spec["usecases"], 2):
        apart_x = abs(a["x"] - b["x"]) >= a["rx"] + b["rx"]
        apart_y = abs(a["y"] - b["y"]) >= a["ry"] + b["ry"]
        assert apart_x or apart_y, (a["id"], b["id"])
    box = spec["boundary"]
    for uc in spec["usecases"]:
        assert box["x"] < uc["x"] - uc["rx"] and uc["x"] + uc["rx"] < box["x"] + box["w"]
        assert box["y"] < uc["y"] - uc["ry"] and uc["y"] + uc["ry"] < box["y"] + box["h"]
    for actor in spec["actors"]:
        outside = actor["x"] + actor["half_w"] < box["x"] or actor["x"] - actor["half_w"] > box["x"] + box["w"]
        assert outside, actor["id"]
        assert 0 <= actor["x"] - actor["half_w"] and actor["x"] + actor["half_w"] <= spec["width"]
    sides = {a["id"]: a["side"] for a in spec["actors"]}
    assert sides == {"receptionist": "left", "veterinarian": "left", "pet_owner": "right", "email_service": "right"}


def test_rendering_is_deterministic(example_project):
    assert render_use_case_diagram(example_project)[0] == render_use_case_diagram(example_project)[0]


def test_module_diagram_brings_in_related_use_cases_from_other_modules(example_data):
    example_data["use_cases"][5]["includes"] = ["UC-2.03", "UC-1.05"]   # UC-2.01 now includes a module 1 use case
    project = Project(example_data)
    with_neighbors = {u["id"] for u in build_layout(project, module="M2")["usecases"]}
    alone = {u["id"] for u in build_layout(project, module="M2", neighbors=False)["usecases"]}
    assert "UC-1.05" in with_neighbors and "UC-1.05" not in alone


def test_specialised_use_case_does_not_repeat_inherited_actors(example_data):
    example_data["use_cases"].append({"id": "UC-1.06", "name": "Book follow-up", "module": "M1",
                                      "actors": ["receptionist"], "requirements": ["FR-01"], "specializes": "UC-1.01"})
    spec = build_layout(Project(example_data), module="M1")
    links = [(link["actor"], link["usecase"]) for link in spec["associations"]]
    assert ("receptionist", "UC-1.01") in links and ("receptionist", "UC-1.06") not in links
    assert {"type": "generalization", "from": "UC-1.06", "to": "UC-1.01", "condition": ""} in [
        {k: rel[k] for k in ("type", "from", "to", "condition")} for rel in spec["relations"]]


def test_position_overrides_are_kept_and_crossings_are_reported(example_project):
    spec = build_layout(example_project, module="M1")
    by_id = {u["id"]: u for u in spec["usecases"]}
    # Put "Cancel appointment" right on the line between "Book appointment" and "Send confirmation".
    mid = ((by_id["UC-1.01"]["x"] + by_id["UC-1.05"]["x"]) / 2, (by_id["UC-1.01"]["y"] + by_id["UC-1.05"]["y"]) / 2)
    moved = build_layout(example_project, module="M1", positions={"UC-1.03": list(mid)})
    placed = {u["id"]: (u["x"], u["y"]) for u in moved["usecases"]}
    assert placed["UC-1.03"] == mid
    assert any("crosses use case UC-1.03" in warning for warning in find_crossings(moved))
    ET.fromstring(render(moved))


def test_unknown_selection_is_an_error(example_project):
    with pytest.raises(DiagramError):
        build_layout(example_project, module="M9")
    with pytest.raises(DiagramError):
        build_layout(example_project, use_cases=["UC-9.99"])


def test_labels_follow_the_model_language(example_data):
    example_data["project"]["language"] = "es"
    svg, _ = render_use_case_diagram(Project(example_data), module="M1")
    assert "«sistema»" in svg and "«system»" not in svg


def test_context_diagram(example_data):
    svg = render_context_diagram(Project(example_data))
    ET.fromstring(svg)
    for text in ("Appointment", "Receptionist", "Email service", "Calendar and free slots", "Delivery result"):
        assert text in svg
    without_flows = copy.deepcopy(example_data)
    without_flows["context"] = {}
    with pytest.raises(DiagramError):
        render_context_diagram(Project(without_flows))


@pytest.mark.skipif(not any(shutil.which(tool) for tool in ("rsvg-convert", "inkscape", "magick")),
                    reason="no SVG converter installed")
def test_svg_to_png(example_project, tmp_path):
    svg_file = tmp_path / "diagram.svg"
    svg_file.write_text(render_use_case_diagram(example_project, module="M2")[0], encoding="utf-8")
    png = svg_to_png(svg_file, tmp_path / "diagram.png", width=800)
    assert png_size(png)[0] == 800


def test_repeated_ids_are_drawn_once_and_bad_positions_are_rejected(example_project):
    spec = build_layout(example_project, use_cases=["UC-2.01", "UC-2.01", "UC-2.03"], neighbors=False)
    assert [u["id"] for u in spec["usecases"]] == ["UC-2.01", "UC-2.03"]
    for bad in ({"UC-1.01": [100]}, {"UC-1.01": "here"}, {"UC-1.01": [1, "x"]}):
        with pytest.raises(DiagramError, match="positions"):
            build_layout(example_project, module="M1", positions=bad)


def test_many_same_column_relations_stay_on_the_outline(example_data):
    hub = example_data["use_cases"][0]                      # UC-1.01, same column as the other receptionist cases
    for number in range(6, 12):
        example_data["use_cases"].append({"id": f"UC-1.{number:02d}", "name": f"Extra goal {number}", "module": "M1",
                                          "actors": ["receptionist"], "requirements": ["FR-01"],
                                          "extends": [{"target": hub["id"], "condition": "x"}]})
    spec = build_layout(Project(example_data), module="M1")
    hub_shape = next(u for u in spec["usecases"] if u["id"] == hub["id"])
    offsets = [rel["to_dy"] for rel in spec["relations"] if rel.get("to") == hub["id"] and "to_dy" in rel]
    assert len(offsets) >= 6 and all(abs(dy) <= 0.8 * hub_shape["ry"] for dy in offsets)


@pytest.mark.skipif(not any(shutil.which(tool) for tool in ("rsvg-convert", "inkscape", "magick")),
                    reason="no SVG converter installed")
def test_converter_failures_are_reported_as_render_errors(tmp_path):
    from sedocs_ai.raster import RenderError

    broken = tmp_path / "broken.svg"
    broken.write_text("this is not svg", encoding="utf-8")
    with pytest.raises(RenderError, match="could not convert"):
        svg_to_png(broken, tmp_path / "broken.png")
