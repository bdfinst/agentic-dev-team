"""No tracked file outside history references the removed ceiling hook (#2177, ADR 0043)."""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(
    0,
    str(REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import repo_invariants

_STALE = "see hooks/" + "context_ceiling_" + "guard.py for details\n"


def _fake_repo(monkeypatch, tmp_path, files):
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    monkeypatch.setattr(repo_invariants, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(repo_invariants, "_tracked_files", lambda: sorted(files))


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


@pytest.mark.parametrize("name", ["context_ceiling_" + "guard", "context_ceiling_" + "report"])
def test_both_removed_names_are_flagged(monkeypatch, tmp_path, name):
    _fake_repo(monkeypatch, tmp_path, {"notes.txt": f"run {name}.py\n"})
    assert len(repo_invariants.check_no_live_ceiling_refs()) == 1


@pytest.mark.parametrize(
    "rel",
    ["docs/adr/0011-old.md", "plugins/dev-team/CHANGELOG.md"],
)
def test_history_is_exempt(monkeypatch, tmp_path, rel):
    _fake_repo(monkeypatch, tmp_path, {rel: _STALE})
    assert repo_invariants.check_no_live_ceiling_refs() == []


def test_changed_files_argument_is_ignored(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"docs/guide.md": _STALE})
    assert repo_invariants.check_no_live_ceiling_refs(["other.md"]) == (
        repo_invariants.check_no_live_ceiling_refs(None)
    )


def test_binary_tracked_file_does_not_crash(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"blob.bin": ""})
    (tmp_path / "blob.bin").write_bytes(b"\x1f\x8b\x08\x00\xff\xfe")
    assert repo_invariants.check_no_live_ceiling_refs() == []


def test_unreadable_or_missing_tracked_file_does_not_crash(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path, {"a.md": "fine\n"})
    monkeypatch.setattr(repo_invariants, "_tracked_files", lambda: ["a.md", "gone.md"])
    assert repo_invariants.check_no_live_ceiling_refs() == []
