"""Unit + byte-parity tests for scripts/plan_waves.py (#589).

Follows the same pattern as test_plan_parse.py: a small number of API-level
behavioural cases plus a parametrized byte-parity comparison against
`plan-waves.sh` for every fixture under `tests/fixtures/plans/`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import plan_waves  # noqa: E402


_PLAN_WAVES_SH = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "plan-waves.sh"
_PLAN_WAVES_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "plan_waves.py"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "plans"


# ---------------------------------------------------------------------------
# API-level behavioural tests
# ---------------------------------------------------------------------------


def test_compute_waves_returns_schema(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `a.ts`\n"
        "### Slice B: beta\n"
        "**Depends-on:** A\n"
        "**Files:** `b.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["schema"] == "plan-waves/v1"
    assert payload["waves"] == [["A"], ["B"]]
    assert payload["slices"]["A"]["wave"] == 1
    assert payload["slices"]["B"]["depends_on"] == ["A"]


def test_compute_waves_flags_collisions(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n"
        "**Depends-on:** none\n"
        "**Files:** `shared.ts`\n"
        "### Slice B: beta\n"
        "**Depends-on:** none\n"
        "**Files:** `shared.ts`\n"
    )
    payload = plan_waves.compute_waves(plan)
    assert payload["collisions"] == [
        {"wave": 1, "slices": ["A", "B"], "file": "shared.ts"}
    ]


def test_compute_waves_rejects_missing_depends(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text("### Slice A: alpha\n**Files:** `a.ts`\n")
    with pytest.raises(SystemExit) as excinfo:
        plan_waves.compute_waves(plan)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "missing its Depends-on declaration" in err


def test_compute_waves_rejects_unknown_reference(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n**Depends-on:** none\n"
        "### Slice B: beta\n**Depends-on:** Z\n"
    )
    with pytest.raises(SystemExit):
        plan_waves.compute_waves(plan)
    err = capsys.readouterr().err
    assert "depends on unknown slice" in err


def test_compute_waves_rejects_cycle(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "### Slice A: alpha\n**Depends-on:** B\n### Slice B: beta\n**Depends-on:** A\n"
    )
    with pytest.raises(SystemExit):
        plan_waves.compute_waves(plan)
    err = capsys.readouterr().err
    assert "dependency cycle" in err


def test_compute_waves_rejects_empty_plan(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text("no slice headers here\n")
    with pytest.raises(SystemExit):
        plan_waves.compute_waves(plan)
    err = capsys.readouterr().err
    assert "no slices found" in err


# ---------------------------------------------------------------------------
# Byte-parity against plan-waves.sh
# ---------------------------------------------------------------------------


def _fixture_paths():
    if not _FIXTURES_DIR.is_dir():
        return []
    return sorted(_FIXTURES_DIR.glob("*.md"))


_FIXTURES = _fixture_paths()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required for parity")
@pytest.mark.skipif(not _PLAN_WAVES_SH.is_file(), reason="plan-waves.sh not present")
@pytest.mark.skipif(not _FIXTURES, reason="no plan fixtures present")
@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda p: p.name)
def test_byte_parity_with_bash(fixture: Path) -> None:
    sh = subprocess.run(
        ["bash", str(_PLAN_WAVES_SH), str(fixture)],
        capture_output=True,
        check=False,
    )
    py = subprocess.run(
        [sys.executable, str(_PLAN_WAVES_PY), str(fixture)],
        capture_output=True,
        check=False,
    )
    assert sh.returncode == py.returncode
    assert py.stdout == sh.stdout, (
        f"stdout diverged on {fixture.name}\nsh: {sh.stdout!r}\npy: {py.stdout!r}"
    )
    # stderr is compared verbatim — plan-waves errors go there.
    assert py.stderr == sh.stderr, (
        f"stderr diverged on {fixture.name}\nsh: {sh.stderr!r}\npy: {py.stderr!r}"
    )
