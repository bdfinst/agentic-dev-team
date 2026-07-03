"""Tests for plugins/dev-team/scripts/detect_bdd_convention.py (issue #537).

Slice 1 of plans/plan-gherkin-feature-persistence.md: deterministic detection
of a target project's BDD convention. Precedence is existing .feature files >
BDD dependency in a manifest > none, always preferring a false negative (no
signal, which prompts the operator) over a false positive (writing derived
.feature files into the wrong directory).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the script's dir is on the path so we can import it as a module.
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import detect_bdd_convention  # type: ignore[import-not-found]  # noqa: E402


def _touch(root: Path, relpath: str, content: str = "") -> Path:
    """Create (and return) a fixture file at root/relpath, making parents."""
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _no_signal() -> dict:
    return {"signal": "none", "framework": None, "dir": None}


# ---------------------------------------------------------------------------
# Feature-file scan — signal "feature-files"
# ---------------------------------------------------------------------------


class TestFeatureFileScan:
    def test_single_root_of_feature_files_is_detected_without_a_manifest(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "specs/features/login.feature", "Feature: login\n")
        _touch(tmp_path, "specs/features/logout.feature", "Feature: logout\n")

        assert detect_bdd_convention.detect(tmp_path) == {
            "signal": "feature-files",
            "framework": None,
            "dir": "specs/features",
        }

    def test_nested_feature_files_report_their_common_directory(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "specs/features/auth/login.feature", "Feature: login\n")
        _touch(tmp_path, "specs/features/billing/invoice.feature", "Feature: invoice\n")

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "feature-files"
        assert result["dir"] == "specs/features"

    @pytest.mark.parametrize(
        "vendored_root",
        [
            "node_modules/some-dep",
            "vendor/some-dep",
            "dist",
            "build",
            ".git/info",
        ],
    )
    def test_feature_files_only_under_vendored_trees_yield_none(
        self, tmp_path: Path, vendored_root: str
    ) -> None:
        _touch(tmp_path, vendored_root + "/features/x.feature", "Feature: x\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_feature_files_only_inside_a_virtualenv_yield_none(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, ".venv/pyvenv.cfg", "home = /usr/bin\n")
        _touch(
            tmp_path,
            ".venv/lib/site-packages/some-dep/features/x.feature",
            "Feature: x\n",
        )

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_vendored_feature_files_do_not_count_as_a_second_root(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "specs/features/login.feature", "Feature: login\n")
        _touch(tmp_path, "node_modules/some-dep/features/x.feature", "Feature: x\n")

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "feature-files"
        assert result["dir"] == "specs/features"

    def test_feature_files_under_multiple_unrelated_roots_yield_none(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "svc-a/features/a.feature", "Feature: a\n")
        _touch(tmp_path, "svc-b/specs/b.feature", "Feature: b\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_feature_files_at_the_project_root_are_too_ambiguous_to_claim(
        self, tmp_path: Path
    ) -> None:
        """A root-level .feature file would make the repo root the destination
        — conservative rule: no signal, prompt instead."""
        _touch(tmp_path, "orphan.feature", "Feature: orphan\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_project_with_no_bdd_markers_yields_none_and_null_dir(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "src/app.py", "print('hello')\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()
