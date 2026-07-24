"""Markdown reference sensor.

A skill/agent/knowledge file that names another repo file by a path which
resolves to the wrong place (a rename left behind, a bare `knowledge/x.md`
from a subdir that the runtime reads file-relative) dangles silently until
something reads it and fails - the class that broke /ship's decision-defaults
screen. scripts/check_md_references.py fails loudly on it, and is
self-maintaining: it keys off the live `git` file tree, so references to
things that are not repo files (runtime artifacts, placeholders) need no
allowlist and are ignored automatically.

Ported from tests/repo/md_reference_tests.bats (#673).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

CHECK = REPO_ROOT / "scripts" / "check_md_references.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _fixture(tmp_path: Path) -> Path:
    fix = tmp_path / "fixture"
    (fix / "plugins" / "dev-team" / "skills" / "demo").mkdir(parents=True)
    (fix / "plugins" / "dev-team" / "knowledge" / "aa").mkdir(parents=True)
    (fix / "plugins" / "dev-team" / "knowledge" / "aa" / "bb.md").write_text(
        "real knowledge file\n"
    )
    return fix


def _write_skill(fix: Path, content: str) -> None:
    (fix / "plugins" / "dev-team" / "skills" / "demo" / "SKILL.md").write_text(content)


def test_the_real_repository_tree_has_no_misrouted_references() -> None:
    result = _run("--root", str(REPO_ROOT))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_correctly_routed_file_relative_reference_passes(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    _write_skill(fix, "See [bb](../../knowledge/aa/bb.md) for details.\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_bare_plugin_root_relative_reference_passes(tmp_path: Path) -> None:
    # Resolves at the module root, so it is not a broken link.
    fix = _fixture(tmp_path)
    _write_skill(fix, "See `knowledge/aa/bb.md` for details.\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_misrouted_reference_to_a_real_file_fails(tmp_path: Path) -> None:
    # `aa/bb.md` resolves nowhere from skills/demo, yet a real file ends with
    # /aa/bb.md.
    fix = _fixture(tmp_path)
    _write_skill(fix, "See `aa/bb.md` for details.\n")
    result = _run("--root", str(fix))
    assert result.returncode == 1
    assert "aa/bb.md" in result.stdout + result.stderr


def test_a_reference_to_a_tracked_path_resolves_even_if_filesystem_cant(
    tmp_path: Path,
) -> None:
    # Reproduces the macOS-vs-CI split: a tracked symlink (e.g.
    # .claude/evals/fixtures -> evals/...) that a CI checkout leaves
    # unmaterialized reads as dangling via os.path but IS a real tracked
    # path. A broken symlink to a directory models that - the walk lists it
    # (so it counts as tracked) yet os.path.isdir is false.
    fix = _fixture(tmp_path)
    (fix / "data").mkdir()
    (fix / "data" / "store").symlink_to("nonexistent-target")
    _write_skill(fix, "Fixtures live in `data/store/` at runtime.\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_reference_that_names_nothing_real_is_ignored(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    _write_skill(fix, "State is written to `memory/decisions.md` at runtime.\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_placeholder_path_is_ignored(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    _write_skill(fix, "A knowledge file (`knowledge/X.md`) is read on demand.\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_backtick_link_label_is_not_checked_only_the_link_target(
    tmp_path: Path,
) -> None:
    # Label text `aa/bb.md` would be a misroute if checked, but it is display
    # text; the actual target resolves, so the line is clean.
    fix = _fixture(tmp_path)
    _write_skill(fix, "See [`aa/bb.md`](../../knowledge/aa/bb.md).\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_fenced_code_block_is_not_scanned(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    _write_skill(fix, "```\nexample: `aa/bb.md` shown as a sample\n```\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_external_url_is_ignored(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    _write_skill(fix, "Docs at https://example.com/aa/bb.md are external.\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_valid_anchor_reference_passes(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    (fix / "plugins" / "dev-team" / "knowledge" / "aa" / "bb.md").write_text(
        "# Overview\n\n## Getting Started\n\nSome content here.\n"
    )
    _write_skill(fix, "See [Getting Started](../../knowledge/aa/bb.md#getting-started).\n")
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_broken_anchor_reference_fails(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    (fix / "plugins" / "dev-team" / "knowledge" / "aa" / "bb.md").write_text(
        "# Overview\n\n## Getting Started\n\nSome content here.\n"
    )
    _write_skill(
        fix, "See [Configuration](../../knowledge/aa/bb.md#configuration).\n"
    )
    result = _run("--root", str(fix))
    assert result.returncode == 1
    assert "anchor does not exist" in result.stdout + result.stderr
    assert "configuration" in result.stdout + result.stderr


def test_anchor_with_code_spans_is_normalized_correctly(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    (fix / "plugins" / "dev-team" / "knowledge" / "aa" / "bb.md").write_text(
        "# Overview\n\n## Configure `--since` flag\n\nSome content here.\n"
    )
    _write_skill(
        fix, "See [Flag Guide](../../knowledge/aa/bb.md#configure-since-flag).\n"
    )
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_anchor_reference_to_nonexistent_file_is_ignored(tmp_path: Path) -> None:
    # When the FILE doesn't exist in the repo, the reference is ignored
    # (it names nothing real). No error is raised.
    fix = _fixture(tmp_path)
    _write_skill(
        fix,
        "See [Getting Started](../../knowledge/nonexistent.md#getting-started).\n",
    )
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_anchor_in_code_fence_is_not_validated(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    (fix / "plugins" / "dev-team" / "knowledge" / "aa" / "bb.md").write_text(
        "# Overview\n\nSome content here.\n"
    )
    _write_skill(
        fix,
        "```\n[link](../../knowledge/aa/bb.md#nonexistent)\n```\n",
    )
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr


def test_multiple_headings_with_similar_names(tmp_path: Path) -> None:
    fix = _fixture(tmp_path)
    (fix / "plugins" / "dev-team" / "knowledge" / "aa" / "bb.md").write_text(
        "# Overview\n\n## Configuration\n\n## Configure Logs\n\nContent.\n"
    )
    _write_skill(
        fix, "See [Logs](../../knowledge/aa/bb.md#configure-logs).\n"
    )
    result = _run("--root", str(fix))
    assert result.returncode == 0, result.stdout + result.stderr
