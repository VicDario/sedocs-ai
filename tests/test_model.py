import copy

import pytest

from sedocs_ai.model import ModelError, Project, has_errors, load_project, validate


def codes(issues, level=None):
    return [i.code for i in issues if level is None or i.level == level]


def test_example_project_is_valid(example_project):
    issues = validate(example_project)
    assert not has_errors(issues), [str(i) for i in issues]
    assert codes(issues, "warning") == []


def test_duplicate_ids_are_errors(example_data):
    example_data["use_cases"].append(copy.deepcopy(example_data["use_cases"][0]))
    issues = validate(Project(example_data))
    assert "duplicate-id" in codes(issues, "error")


def test_unknown_references_are_errors(example_data):
    uc = example_data["use_cases"][0]
    uc["actors"] = ["ghost"]
    uc["requirements"] = ["FR-99"]
    uc["includes"] = ["UC-9.99"]
    uc["module"] = "M9"
    found = codes(validate(Project(example_data)), "error")
    assert {"unknown-actor", "unknown-requirement", "unknown-use-case", "unknown-module"} <= set(found)


def test_self_reference_and_include_cycle(example_data):
    first, second = example_data["use_cases"][0], example_data["use_cases"][1]
    first["includes"] = [second["id"]]
    second["includes"] = [first["id"]]
    second["extends"] = [{"target": second["id"]}]
    found = codes(validate(Project(example_data)), "error")
    assert "include-cycle" in found and "self-reference" in found


def test_gaps_are_warnings_not_errors(example_data):
    example_data["requirements"]["functional"].append({"id": "FR-77", "name": "Export data"})
    example_data["actors"].append({"id": "auditor", "name": "Auditor"})
    example_data["use_cases"].append({"id": "UC-9.01", "name": "Do something"})
    issues = validate(Project(example_data))
    assert not has_errors(issues)
    assert {"uncovered-requirement", "unused-actor", "orphan-use-case", "untraced-use-case"} <= set(codes(issues, "warning"))


def test_extends_accepts_plain_ids_and_conditions(example_data):
    uc = example_data["use_cases"][0]
    uc["extends"] = ["UC-1.02", {"target": "UC-1.03", "condition": "slot is taken"}]
    project = Project(example_data)
    assert project.use_cases[0]["extends"] == [
        {"target": "UC-1.02", "condition": ""},
        {"target": "UC-1.03", "condition": "slot is taken"},
    ]


def test_unreadable_models_raise(tmp_path):
    bad = tmp_path / "project.yaml"
    bad.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ModelError):
        load_project(bad)
    with pytest.raises(ModelError):
        load_project(tmp_path / "missing.yaml")
    with pytest.raises(ModelError):
        Project({"project": {"name": "X", "language": "fr"}})
