"""Each skill follows the same contract: complete frontmatter, fixed sections, small body, local references."""
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
SECTIONS = ["Activation Contract", "Hard Rules", "Decision Gates", "Execution Steps", "Output Contract", "References"]


def parts(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    _, front, body = text.split("---\n", 2)
    return yaml.safe_load(front), body


def test_the_expected_skills_exist():
    assert [p.parent.name for p in SKILLS] == ["sedocs", "sedocs-document", "sedocs-use-cases"]


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_skill_contract(path):
    front, body = parts(path)
    assert front["name"] == path.parent.name
    assert front["license"] == "Apache-2.0" and front["metadata"]["author"] and front["metadata"]["version"]
    description = front["description"]
    assert description.startswith("Trigger: ") and len(description) <= 250 and "\n" not in description
    assert re.findall(r"^## (.+)$", body, flags=re.M) == SECTIONS
    assert len(body.split()) * 1.35 <= 1000, "skill body over the 1000-token budget"
    for reference in re.findall(r"`(references/[^`]+)`", body):
        assert (path.parent / reference).is_file(), reference
    for command in re.findall(r"`sedocs ([a-z]+)", body):
        assert command in {"init", "check", "render", "build", "preview", "inspect", "doctor"}, command


def test_plugin_manifests_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    entry = market["plugins"][0]
    assert entry["name"] == plugin["name"] == "sedocs-ai" and entry["source"] == "./"
    assert market["owner"]["name"] and entry["version"] == plugin["version"]
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{plugin["version"]}"' in project
