"""Tests for specs_convention_marker.py (#986).

Classify whether a project's root CLAUDE.md has opted into the issue-first
specs convention ("Specs and plans are GitHub issues here, not files") so
/specs only switches to GitHub-issue persistence on a repo that has
explicitly declared the convention, never by default.

Prints exactly one of:
    marker     — root CLAUDE.md exists and contains the marker phrase
    no-marker  — root CLAUDE.md exists but does not contain the marker phrase
    none       — no root CLAUDE.md found (fail-open: treated the same as
                 "marker absent" by callers, never blocks)

Both the module API (``has_marker(text)`` / ``classify(claude_md_path)``) and
the CLI entry point (with an optional path override for testing, and the
git-repo-root resolution + fail-open behavior otherwise) are covered.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the script's dir is on the path so we can import it as a module.
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import specs_convention_marker  # type: ignore[import-not-found]

_SCRIPT_PY = _SCRIPT_DIR / "specs_convention_marker.py"


# ---------------------------------------------------------------------------
# has_marker() — the pure library function
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Specs and plans are GitHub issues here, not files.", True),
        (
            "- **Specs and plans are GitHub issues here, not files.** When "
            "developing this repo...",
            True,
        ),
        ("SPECS AND PLANS ARE GITHUB ISSUES HERE, NOT FILES", True),
        ("specs and plans are github issues here, not files", True),
        ("", False),
        ("This repo uses GitHub for everything.", False),
        ("Specs live in docs/specs/.", False),
    ],
)
def test_has_marker(text: str, expected: bool) -> None:
    assert specs_convention_marker.has_marker(text) == expected


# ---------------------------------------------------------------------------
# classify() — the pure library function over a path
# ---------------------------------------------------------------------------


def test_classify_marker_present(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# Working Rules\n\n"
        "- **Specs and plans are GitHub issues here, not files.** Fall back "
        "to untracked files only when there is no GitHub connection.\n",
        encoding="utf-8",
    )
    assert specs_convention_marker.classify(claude_md) == "marker"


def test_classify_marker_absent(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Just some other project instructions.\n", encoding="utf-8")
    assert specs_convention_marker.classify(claude_md) == "no-marker"


def test_classify_missing_file(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    assert not claude_md.exists()
    assert specs_convention_marker.classify(claude_md) == "none"


def test_classify_none_path() -> None:
    assert specs_convention_marker.classify(None) == "none"


# ---------------------------------------------------------------------------
# CLI — argv[1] path override + repo-root resolution + fail-open
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )


def test_cli_argv_override_marker(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "Specs and plans are GitHub issues here, not files.\n", encoding="utf-8"
    )
    r = _run_cli(str(claude_md))
    assert r.returncode == 0
    assert r.stdout.strip() == "marker"


def test_cli_argv_override_no_marker(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("Nothing relevant here.\n", encoding="utf-8")
    r = _run_cli(str(claude_md))
    assert r.returncode == 0
    assert r.stdout.strip() == "no-marker"


def test_cli_argv_override_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"
    r = _run_cli(str(missing))
    assert r.returncode == 0
    assert r.stdout.strip() == "none"


def test_cli_no_root_claude_md_is_none_fail_open(tmp_path: Path) -> None:
    """A repo root with no CLAUDE.md at all is ``none`` (fail-open, never blocks)."""
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env={
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
        },
    )
    r = _run_cli(cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "none"


def test_cli_root_claude_md_with_marker(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env={
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
        },
    )
    (tmp_path / "CLAUDE.md").write_text(
        "Specs and plans are GitHub issues here, not files.\n", encoding="utf-8"
    )
    r = _run_cli(cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "marker"


def test_cli_outside_git_repo_is_none_fail_open(tmp_path: Path) -> None:
    """Fail-open outside any git repo — never blocks, mirrors git_origin_host.py."""
    r = _run_cli(cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "none"
