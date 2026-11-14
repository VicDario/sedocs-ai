from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "harbor-clinic"


@pytest.fixture
def example_data() -> dict:
    return yaml.safe_load((EXAMPLE / "project.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def example_project(example_data):
    from sedocs_ai.model import Project

    return Project(example_data, EXAMPLE / "project.yaml")
