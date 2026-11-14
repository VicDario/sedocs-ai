"""The repository must never carry personal data: this runs the same scan as the commit hook."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True).returncode != 0,
                    reason="not a git checkout")
def test_tracked_files_pass_the_privacy_scan(capsys):
    spec = importlib.util.spec_from_file_location("privacy_scan", ROOT / "scripts" / "privacy_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0, capsys.readouterr().out
