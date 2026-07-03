"""Unit tests for plugins/dev-team/scripts/plan_gherkin_export.py.

Behavioral contract (Slice 2 of plans/plan-gherkin-feature-persistence.md):
each `### Slice N:` section's fenced ```gherkin block is exported to
`<dir>/<plan-slug>/slice-<N>-<slice-slug>.feature`, byte-for-byte identical
to the fenced block modulo exactly one trailing newline, with no added
header — and the run always reports what it did.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure the script's dir is on the path so we can import it as a module.
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import plan_gherkin_export  # type: ignore[import-not-found]  # noqa: E402


_SLICE_ONE_GHERKIN = """\
Feature: Fancy widget
  Scenario: it works
    Given a widget
    Then it works
"""

_SLICE_TWO_GHERKIN = """\
Feature: CLI reporting
  Scenario: the run reports
    When the export runs
    Then the output reports the destination
"""


def _plan_text(decision_line: str = "**Gherkin persistence**: features") -> str:
    """A minimal two-slice plan in the plan-template shape."""
    return (
        "# Plan: Sample widget\n"
        "\n"
        "**Created**: 2026-07-03\n"
        "**Status**: approved\n"
        + (decision_line + "\n" if decision_line else "")
        + "\n"
        "## Goal\n"
        "\n"
        "Sample goal.\n"
        "\n"
        "## Slices\n"
        "\n"
        "### Slice 1: Fancy Widget API!\n"
        "\n"
        "**Depends-on:** none\n"
        "**Files:** `a.py`\n"
        "\n"
        "**Behavior:**\n"
        "\n"
        "```gherkin\n"
        + _SLICE_ONE_GHERKIN
        + "```\n"
        "\n"
        "**Steps:**\n"
        "\n"
        "#### Step 1.1: Do the thing\n"
        "\n"
        "**Commit**: `feat: thing`\n"
        "\n"
        "### Slice 2: CLI & reporting\n"
        "\n"
        "**Depends-on:** 1\n"
        "**Files:** `b.py`\n"
        "\n"
        "**Behavior:**\n"
        "\n"
        "```gherkin\n"
        + _SLICE_TWO_GHERKIN
        + "```\n"
        "\n"
        "## Parallelization\n"
        "\n"
        "```mermaid\n"
        "graph TD\n"
        "  S1 --> S2\n"
        "```\n"
    )


def _write_plan(tmp_path: Path, name: str = "plan-sample-widget.md", **kwargs) -> Path:
    plan = tmp_path / name
    plan.write_text(_plan_text(**kwargs), encoding="utf-8")
    return plan


# ---------------------------------------------------------------------------
# Step 2.1 — byte-for-byte export to exact filenames
# ---------------------------------------------------------------------------


def test_exports_each_slice_gherkin_to_exact_filenames(tmp_path: Path) -> None:
    """plan-slug is the filename stem verbatim; slice-slug is the lowercased
    title with non-alphanumeric runs collapsed to single hyphens, trimmed."""
    plan = _write_plan(tmp_path)
    plan_gherkin_export.export_plan(plan, tmp_path)
    out_dir = tmp_path / "features" / "plan-sample-widget"
    assert (out_dir / "slice-1-fancy-widget-api.feature").is_file()
    assert (out_dir / "slice-2-cli-reporting.feature").is_file()
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "slice-1-fancy-widget-api.feature",
        "slice-2-cli-reporting.feature",
    ]


def test_exported_content_is_byte_for_byte_with_one_trailing_newline(
    tmp_path: Path,
) -> None:
    """No header, comment, or annotation — the fenced block verbatim."""
    plan = _write_plan(tmp_path)
    plan_gherkin_export.export_plan(plan, tmp_path)
    out_dir = tmp_path / "features" / "plan-sample-widget"
    one = (out_dir / "slice-1-fancy-widget-api.feature").read_text(encoding="utf-8")
    two = (out_dir / "slice-2-cli-reporting.feature").read_text(encoding="utf-8")
    assert one == _SLICE_ONE_GHERKIN
    assert two == _SLICE_TWO_GHERKIN


def test_report_names_destination_and_written_count(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path)
    report = "\n".join(plan_gherkin_export.export_plan(plan, tmp_path))
    assert "destination: features/plan-sample-widget" in report
    assert "files written: 2" in report


# ---------------------------------------------------------------------------
# Step 2.2 — decision parsing, no-op modes, and overwrite reporting
# ---------------------------------------------------------------------------


def _tree_snapshot(root: Path) -> list:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_plan_file_only_decision_writes_nothing_and_notes_it(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path, decision_line="**Gherkin persistence**: plan-file-only"
    )
    before = _tree_snapshot(tmp_path)
    report = "\n".join(plan_gherkin_export.export_plan(plan, tmp_path))
    assert _tree_snapshot(tmp_path) == before
    assert "plan-file-only" in report
    assert "nothing to export" in report


def test_missing_decision_writes_nothing_and_notes_it(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, decision_line="")
    before = _tree_snapshot(tmp_path)
    report = "\n".join(plan_gherkin_export.export_plan(plan, tmp_path))
    assert _tree_snapshot(tmp_path) == before
    assert "no Gherkin persistence decision recorded" in report
    assert "nothing to export" in report


def test_custom_path_decision_resolves_to_its_path(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path, decision_line="**Gherkin persistence**: custom: e2e/specs"
    )
    report = "\n".join(plan_gherkin_export.export_plan(plan, tmp_path))
    out_dir = tmp_path / "e2e" / "specs" / "plan-sample-widget"
    assert (out_dir / "slice-1-fancy-widget-api.feature").is_file()
    assert "destination: e2e/specs/plan-sample-widget" in report


def test_reexport_overwrites_and_reports_count(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path)
    out_dir = tmp_path / "features" / "plan-sample-widget"
    out_dir.mkdir(parents=True)
    (out_dir / "slice-1-fancy-widget-api.feature").write_text(
        "Feature: outdated\n", encoding="utf-8"
    )
    (out_dir / "slice-2-cli-reporting.feature").write_text(
        "Feature: outdated\n", encoding="utf-8"
    )
    report = "\n".join(plan_gherkin_export.export_plan(plan, tmp_path))
    content = (out_dir / "slice-1-fancy-widget-api.feature").read_text(
        encoding="utf-8"
    )
    assert content == _SLICE_ONE_GHERKIN
    assert "overwritten: 2" in report


def test_reexport_removes_stale_features_and_reports_count(tmp_path: Path) -> None:
    """Stale files from renamed or renumbered slices never linger."""
    plan = _write_plan(tmp_path)
    out_dir = tmp_path / "features" / "plan-sample-widget"
    out_dir.mkdir(parents=True)
    stale = out_dir / "slice-3-renamed-away.feature"
    stale.write_text("Feature: stale\n", encoding="utf-8")
    report = "\n".join(plan_gherkin_export.export_plan(plan, tmp_path))
    assert not stale.exists()
    assert "slice-3-renamed-away.feature" in report
    assert "stale removed: 1" in report


def test_fresh_export_reports_zero_overwrites_and_removals(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path)
    report = "\n".join(plan_gherkin_export.export_plan(plan, tmp_path))
    assert "overwritten: 0" in report
    assert "stale removed: 0" in report


def test_non_feature_files_in_tool_owned_dir_survive(tmp_path: Path) -> None:
    """Only *.feature files are cleared from the tool-owned subdirectory."""
    plan = _write_plan(tmp_path)
    out_dir = tmp_path / "features" / "plan-sample-widget"
    out_dir.mkdir(parents=True)
    keeper = out_dir / "README.md"
    keeper.write_text("not a derived file\n", encoding="utf-8")
    plan_gherkin_export.export_plan(plan, tmp_path)
    assert keeper.read_text(encoding="utf-8") == "not a derived file\n"


# ---------------------------------------------------------------------------
# Step 2.3 — failure paths and CLI contract
# ---------------------------------------------------------------------------

_SCRIPT_PY = _SCRIPT_DIR / "plan_gherkin_export.py"


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        check=False,
    )


def test_cli_valid_run_exits_zero_and_prints_report(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path)
    result = _run_cli(str(plan), cwd=tmp_path)
    assert result.returncode == 0
    assert "destination: features/plan-sample-widget" in result.stdout
    assert "files written: 2" in result.stdout
    out_dir = tmp_path / "features" / "plan-sample-widget"
    assert (out_dir / "slice-1-fancy-widget-api.feature").is_file()


def test_cli_plan_file_only_exits_zero_with_note(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path, decision_line="**Gherkin persistence**: plan-file-only"
    )
    result = _run_cli(str(plan), cwd=tmp_path)
    assert result.returncode == 0
    assert "nothing to export" in result.stdout


def test_cli_destination_dir_collision_exits_nonzero_naming_path(
    tmp_path: Path,
) -> None:
    """The destination directory itself is an existing non-directory file."""
    plan = _write_plan(tmp_path)
    (tmp_path / "features").write_text("in the way\n", encoding="utf-8")
    result = _run_cli(str(plan), cwd=tmp_path)
    assert result.returncode != 0
    assert "features" in result.stderr


def test_cli_plan_subdir_collision_exits_nonzero_naming_path(tmp_path: Path) -> None:
    """The tool-owned <dir>/<plan-slug> path is an existing non-directory file."""
    plan = _write_plan(tmp_path)
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "plan-sample-widget").write_text(
        "in the way\n", encoding="utf-8"
    )
    result = _run_cli(str(plan), cwd=tmp_path)
    assert result.returncode != 0
    assert "plan-sample-widget" in result.stderr


def test_cli_missing_plan_file_exits_nonzero_naming_path(tmp_path: Path) -> None:
    result = _run_cli("plans/no-such-plan.md", cwd=tmp_path)
    assert result.returncode != 0
    assert "no-such-plan.md" in result.stderr
