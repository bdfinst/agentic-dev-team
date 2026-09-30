"""authoring_digest: per-diff write-time checklist assembled from review lenses."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import authoring_digest

SCRIPT = ROOT / "scripts" / "authoring_digest.py"


def _run(*files):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--files", *files],
        capture_output=True, text=True, check=True,
    ).stdout


def test_extract_stops_at_next_heading():
    text = "## Authoring checklist\n\n- a\n- b\n\n## Self-Challenge\n- not me\n"
    assert authoring_digest.extract_checklist(text) == ["- a", "- b"]


def test_extract_absent_returns_empty():
    assert authoring_digest.extract_checklist("## Detect\n- x\n") == []


def test_python_diff_includes_core_lens_excludes_frontend_lens():
    out = _run("src/app.py")
    assert "### correctness-review" in out
    assert "### a11y-review" not in out


def test_no_files_yields_empty_digest():
    assert _run() == ""


def test_every_checklist_is_terse():
    for f in (ROOT / "agents").glob("*-review.md"):
        bullets = authoring_digest.extract_checklist(f.read_text(encoding="utf-8"))
        assert len(bullets) <= 8, f.name
