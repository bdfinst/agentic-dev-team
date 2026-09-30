"""No tracked file outside history references the removed ceiling hook (#2177, ADR 0043)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(
    0,
    str(REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import repo_invariants

_STALE = "see hooks/" + "context_ceiling_" + "guard.py for details\n"
_MARKER = Path(".claude-plugin") / "marketplace.json"


def _fake_repo(monkeypatch, tmp_path, files, *, marketplace=True):
    files = dict(files)
    if marketplace:
        files[str(_MARKER)] = "{}\n"
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    monkeypatch.setattr(repo_invariants, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(repo_invariants, "_tracked_files", lambda: sorted(files))


def _flagged(monkeypatch, tmp_path, files):
    _fake_repo(monkeypatch, tmp_path, files)
    return [f["file"] for f in repo_invariants.check_no_live_ceiling_refs()]


def test_check_is_registered():
    assert repo_invariants.check_no_live_ceiling_refs in repo_invariants.CHECKS


def test_real_repo_is_clean():
    assert repo_invariants.check_no_live_ceiling_refs() == []


def test_a_stale_reference_is_flagged(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"docs/guide.md": _STALE})
    findings = repo_invariants.check_no_live_ceiling_refs()
    assert [(f["invariant"], f["file"]) for f in findings] == [
        ("no-live-ceiling-refs", "docs/guide.md")
    ]


@pytest.mark.parametrize(
    "text",
    [
        "run context_ceiling_" + "guard.py",
        "run context_ceiling_" + "report.py",
        "see docs/context-ceiling-" + "validation.md",
        "export DEV_TEAM_CONTEXT_" + "ABS_CEILING=1",
    ],
)
def test_each_removed_name_is_flagged(monkeypatch, tmp_path, text):
    assert _flagged(monkeypatch, tmp_path, {"notes.txt": text + "\n"}) == ["notes.txt"]


@pytest.mark.parametrize("rel", ["docs/adr/0011-old.md", "plugins/dev-team/CHANGELOG.md"])
def test_history_is_exempt(monkeypatch, tmp_path, rel):
    assert _flagged(monkeypatch, tmp_path, {rel: _STALE}) == []


@pytest.mark.parametrize("rel", ["tests/other.py", "CHANGELOG.md", "plugins/dev-team/docs/x.md"])
def test_everything_else_is_flagged(monkeypatch, tmp_path, rel):
    assert _flagged(monkeypatch, tmp_path, {rel: _STALE}) == [rel]


def test_changed_files_argument_is_ignored(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"docs/guide.md": _STALE})
    assert repo_invariants.check_no_live_ceiling_refs(["other.md"]) == (
        repo_invariants.check_no_live_ceiling_refs(None)
    )


def test_binary_tracked_file_does_not_crash(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"blob.bin": ""})
    (tmp_path / "blob.bin").write_bytes(b"\x1f\x8b\x08\x00\xff\xfe")
    assert repo_invariants.check_no_live_ceiling_refs() == []


def test_missing_tracked_file_is_skipped(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"a.md": "fine\n"})
    monkeypatch.setattr(repo_invariants, "_tracked_files", lambda: ["a.md", "gone.md"])
    assert repo_invariants.check_no_live_ceiling_refs() == []


def test_oserror_while_reading_is_skipped(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"a.md": _STALE})

    def boom(self):
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_bytes", boom)
    assert repo_invariants.check_no_live_ceiling_refs() == []


def test_size_cap_boundary(monkeypatch, tmp_path):
    cap = repo_invariants._CEILING_REF_MAX_BYTES
    needle = _STALE.encode()
    at_cap = needle + b" " * (cap - len(needle))
    over = at_cap + b" "
    _fake_repo(monkeypatch, tmp_path, {"at_cap.txt": "", "over.txt": ""})
    (tmp_path / "at_cap.txt").write_bytes(at_cap)
    (tmp_path / "over.txt").write_bytes(over)
    assert len(at_cap) == cap
    assert [f["file"] for f in repo_invariants.check_no_live_ceiling_refs()] == ["at_cap.txt"]


def test_downstream_shaped_root_returns_nothing(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"docs/guide.md": _STALE}, marketplace=False)
    assert repo_invariants.check_no_live_ceiling_refs() == []


def test_git_failure_returns_nothing_instead_of_walking(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"docs/guide.md": _STALE})
    monkeypatch.undo()  # drop the stub; re-point the root only
    monkeypatch.setattr(repo_invariants, "_REPO_ROOT", tmp_path)

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    assert repo_invariants._tracked_files() is None
    assert repo_invariants.check_no_live_ceiling_refs() == []
