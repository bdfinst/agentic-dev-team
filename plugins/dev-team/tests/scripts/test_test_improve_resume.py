"""Tests for scripts/test_improve_resume.py — `--from-phase` auto-detect
resume-point resolution for /test-improve (issue #1151)."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
SCRIPT = SCRIPTS_DIR / "test_improve_resume.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from test_improve_resume import (
    build_result,
    derive_slug,
    main,
    scan_phase_files,
    slugify,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_phases(root: Path, *tokens: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for t in tokens:
        (root / f"phase-{t}.md").write_text("done\n", encoding="utf-8")
    return root


def result(root: Path, explicit=None):
    code, payload = build_result(root, explicit)
    return code, payload


# ---------------------------------------------------------------------------
# scan + ordering
# ---------------------------------------------------------------------------

def test_scan_ignores_non_phase_files(tmp_path):
    root = make_phases(tmp_path / "s", "0", "1")
    (root / "gherkin.md").write_text("x", encoding="utf-8")
    (root / "phase-4-review.json").write_text("{}", encoding="utf-8")
    (root / "coverage-history.json").write_text("[]", encoding="utf-8")
    assert scan_phase_files(root) == ["0", "1"]


def test_scan_missing_dir_is_empty(tmp_path):
    assert scan_phase_files(tmp_path / "nope") == []


def test_scan_orders_4b_between_4_and_5(tmp_path):
    root = make_phases(tmp_path / "s", "5", "4b", "4", "3")
    assert scan_phase_files(root) == ["3", "4", "4b", "5"]


# ---------------------------------------------------------------------------
# auto-detect resolution — highest completed + 1
# ---------------------------------------------------------------------------

def test_only_phase_0_resumes_at_1(tmp_path):
    root = make_phases(tmp_path / "s", "0")
    code, payload = result(root)
    assert code == 0
    assert payload["resolved_phase"] == "1"
    assert payload["latest_completed"] == "phase-0.md"


def test_phase_3_resumes_at_4(tmp_path):
    root = make_phases(tmp_path / "s", "0", "1", "2", "3")
    _, payload = result(root)
    assert payload["resolved_phase"] == "4"


def test_no_arg_resolves_to_highest_completed_plus_one(tmp_path):
    root = make_phases(tmp_path / "s", "0", "1", "2")
    _, payload = result(root)
    assert payload["resolved_phase"] == "3"
    assert "latest completed: phase-2.md" in payload["reason"]


# ---------------------------------------------------------------------------
# 4b ordering edge cases
# ---------------------------------------------------------------------------

def test_phase_4_without_4b_resumes_at_4b(tmp_path):
    root = make_phases(tmp_path / "s", "0", "1", "2", "3", "4")
    _, payload = result(root)
    assert payload["resolved_phase"] == "4b"
    assert payload["latest_completed"] == "phase-4.md"


def test_phase_4b_resumes_at_6(tmp_path):
    root = make_phases(tmp_path / "s", "0", "1", "2", "3", "4", "4b")
    _, payload = result(root)
    assert payload["resolved_phase"] == "6"
    assert payload["latest_completed"] == "phase-4b.md"
    assert "phase-4b.md" in payload["message"]


def test_phase_5_resumes_at_6(tmp_path):
    root = make_phases(tmp_path / "s", "0", "1", "2", "3", "4", "4b", "5")
    _, payload = result(root)
    assert payload["resolved_phase"] == "6"


def test_phase_6_resumes_at_7(tmp_path):
    root = make_phases(tmp_path / "s", "0", "4", "4b", "5", "6")
    _, payload = result(root)
    assert payload["resolved_phase"] == "7"


# ---------------------------------------------------------------------------
# completion + error edge cases
# ---------------------------------------------------------------------------

def test_phase_7_reports_complete(tmp_path):
    root = make_phases(tmp_path / "s", "0", "7")
    code, payload = result(root)
    assert code == 0
    assert payload["complete"] is True
    assert payload["resolved_phase"] is None
    assert "complete" in payload["message"].lower()


def test_absent_memory_dir_errors(tmp_path):
    code, payload = result(tmp_path / "does-not-exist")
    assert code == 2
    assert payload["error"]
    assert payload["resolved_phase"] is None
    assert "Phase 0" in payload["message"]


def test_empty_memory_dir_errors(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    code, payload = result(root)
    assert code == 2
    assert "no completed phase files" in payload["message"].lower()


def test_missing_phase_0_errors_even_when_later_phases_exist(tmp_path):
    # Phase-0 inputs are mandatory; --from-phase never re-prompts them.
    root = make_phases(tmp_path / "s", "1", "2")
    code, payload = result(root)
    assert code == 2
    assert payload["resolved_phase"] is None
    assert "phase-0.md" in payload["message"]


# ---------------------------------------------------------------------------
# explicit override
# ---------------------------------------------------------------------------

def test_explicit_number_overrides_autodetect(tmp_path):
    root = make_phases(tmp_path / "s", "0", "1", "2", "3", "4")
    # Auto would pick 4b; explicit forces 2.
    _, auto = result(root)
    assert auto["resolved_phase"] == "4b"
    code, payload = result(root, explicit="2")
    assert code == 0
    assert payload["resolved_phase"] == "2"
    assert "overrides auto-detect" in payload["reason"]


def test_explicit_still_requires_phase_0(tmp_path):
    root = make_phases(tmp_path / "s", "1")
    code, payload = result(root, explicit="5")
    assert code == 2
    assert payload["resolved_phase"] is None


def test_explicit_4b_token_supported(tmp_path):
    root = make_phases(tmp_path / "s", "0", "4")
    _, payload = result(root, explicit="4b")
    assert payload["resolved_phase"] == "4b"


# ---------------------------------------------------------------------------
# slug helpers
# ---------------------------------------------------------------------------

def test_slugify_matches_shared_convention():
    assert slugify("My Repo!") == "my-repo"
    assert slugify("Foo   Bar") == "foo-bar"


def test_derive_slug_uses_last_path_segment(tmp_path):
    d = tmp_path / "Some Project"
    d.mkdir()
    assert derive_slug(str(d)) == "some-project"


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_cli_via_memory_dir(tmp_path, capsys):
    root = make_phases(tmp_path / "s", "0", "1")
    rc = main(["--memory-dir", str(root)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolved_phase"] == "2"


def test_cli_error_exit_code(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--memory-dir", str(tmp_path / "nope")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["error"]
    assert "Phase 0" in proc.stderr


def test_cli_derives_slug_from_repo_path(tmp_path, capsys):
    repo = tmp_path / "widget-lib"
    (repo).mkdir()
    make_phases(tmp_path / "memory" / "test-improve" / "widget-lib", "0", "1", "2")
    rc = main(
        [
            str(repo),
            "--memory-root",
            str(tmp_path / "memory" / "test-improve"),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolved_phase"] == "3"
