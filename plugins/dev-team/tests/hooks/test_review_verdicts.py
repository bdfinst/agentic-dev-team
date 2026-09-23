"""Unit tests for hooks/lib/review_verdicts.py (#2166, Step 2.2).

Covers:
  - `emit_review_verdict()`: append, dir creation, compact single-line JSON,
    optional session_id, fail-open on OSError / arbitrary exceptions.
  - Consent posture (Decision 2): writes happen even with
    `DEV_TEAM_TELEMETRY` unset and an explicit `{"enabled": false}` in
    `~/.claude/telemetry.json`.
  - `load_verdicts()`: write round-trip, and its "no usable rows, never an
    exception" contract for an absent file, a corrupted line, and a
    version-mismatched row.
  - A mechanical content-guard: `load_verdicts` has no consumer other than
    `scripts/verdict_scope.py` (#2167, its first real consumer) and this
    module's own tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOKS_DIR = _PLUGIN_DIR / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_TESTS_LIB = _PLUGIN_DIR / "tests" / "lib"

for _p in (_HOOKS_DIR, _LIB_DIR, _TESTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import plugin_version  # type: ignore[import-not-found]
import review_verdicts  # type: ignore[import-not-found]
import telemetry_consent  # type: ignore[import-not-found]

_LOG_REL = Path(".claude") / "metrics" / "review-verdicts.jsonl"


# ---------------------------------------------------------------------------
# emit_review_verdict() — the writer
# ---------------------------------------------------------------------------


def test_emit_appends_one_compact_jsonl_line_with_expected_fields(
    tmp_path: Path,
) -> None:
    review_verdicts.emit_review_verdict(
        tmp_path, "security-review", "src/foo.py", "abc123", "pass"
    )
    log = tmp_path / _LOG_REL
    assert log.is_file()
    raw = log.read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert len(lines) == 1
    assert raw.endswith("\n")
    # Compact separators: no space after ',' or ':'.
    assert ", " not in lines[0]
    assert '": ' not in lines[0]
    event = json.loads(lines[0])
    assert event["lens"] == "security-review"
    assert event["file_path"] == "src/foo.py"
    assert event["file_content_hash"] == "abc123"
    assert event["outcome"] == "pass"
    assert "ts" in event
    assert event["plugin_version"] == plugin_version.shipped_version()
    assert "session_id" not in event


def test_emit_creates_metrics_dir_when_absent(tmp_path: Path) -> None:
    assert not (tmp_path / ".claude" / "metrics").exists()
    review_verdicts.emit_review_verdict(tmp_path, "security-review", "f.py", "h", "pass")
    assert (tmp_path / ".claude" / "metrics").is_dir()


def test_emit_includes_session_id_when_given(tmp_path: Path) -> None:
    review_verdicts.emit_review_verdict(
        tmp_path, "security-review", "f.py", "h", "pass", session_id="sess-1"
    )
    event = json.loads((tmp_path / _LOG_REL).read_text(encoding="utf-8").splitlines()[0])
    assert event["session_id"] == "sess-1"


def test_emit_appends_not_overwrites_across_two_calls(tmp_path: Path) -> None:
    review_verdicts.emit_review_verdict(tmp_path, "security-review", "a.py", "h1", "pass")
    review_verdicts.emit_review_verdict(
        tmp_path, "structure-review", "b.py", "h2", "findings"
    )
    lines = (tmp_path / _LOG_REL).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    events = [json.loads(ln) for ln in lines]
    assert events[0]["file_path"] == "a.py"
    assert events[1]["file_path"] == "b.py"


def test_emit_fails_open_on_unwritable_metrics_dir(tmp_path: Path) -> None:
    """A `.claude/` that can't hold a `metrics/` subdirectory (e.g. a file
    occupying its path) must not raise — the caller's exit code must never
    be affected."""
    (tmp_path / ".claude").write_text("not a directory")
    review_verdicts.emit_review_verdict(tmp_path, "security-review", "f.py", "h", "pass")


def test_emit_fails_open_on_arbitrary_exception(tmp_path: Path, monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("disk is on fire")

    monkeypatch.setattr(review_verdicts, "_isoformat_utc", _boom)
    review_verdicts.emit_review_verdict(tmp_path, "security-review", "f.py", "h", "pass")
    assert not (tmp_path / _LOG_REL).exists()


# ---------------------------------------------------------------------------
# Consent posture (Decision 2): unconditional, like boundary-events.jsonl.
# ---------------------------------------------------------------------------


def test_emit_writes_even_when_telemetry_consent_is_off(
    tmp_path: Path, monkeypatch
) -> None:
    """Consent-off, demonstrated by test (plan AC): `DEV_TEAM_TELEMETRY` is
    unset AND `~/.claude/telemetry.json` explicitly says `{"enabled":
    false}` — `emit_review_verdict` must still write a row, since this store
    sits outside consent gating entirely (Decision 2)."""
    monkeypatch.delenv("DEV_TEAM_TELEMETRY", raising=False)
    fake_home = tmp_path / "fake-home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude" / "telemetry.json").write_text(
        json.dumps({"enabled": False}), encoding="utf-8"
    )
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    # Sanity: confirm consent really does read as off under this setup —
    # otherwise this test wouldn't prove what it claims to.
    assert telemetry_consent.is_enabled() is False

    project = tmp_path / "project"
    review_verdicts.emit_review_verdict(project, "security-review", "f.py", "h", "pass")
    log = project / _LOG_REL
    assert log.is_file()
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


# ---------------------------------------------------------------------------
# load_verdicts() — the reader
# ---------------------------------------------------------------------------


def test_load_verdicts_round_trips_an_emitted_row(tmp_path: Path) -> None:
    review_verdicts.emit_review_verdict(
        tmp_path, "security-review", "src/foo.py", "abc123", "findings"
    )
    rows = review_verdicts.load_verdicts(tmp_path)
    assert len(rows) == 1
    assert rows[0]["lens"] == "security-review"
    assert rows[0]["file_path"] == "src/foo.py"
    assert rows[0]["file_content_hash"] == "abc123"
    assert rows[0]["outcome"] == "findings"
    assert rows[0]["plugin_version"] == plugin_version.shipped_version()


def test_load_verdicts_absent_file_returns_empty(tmp_path: Path) -> None:
    assert review_verdicts.load_verdicts(tmp_path) == []


def test_load_verdicts_corrupted_line_yields_no_usable_rows(tmp_path: Path) -> None:
    log = tmp_path / _LOG_REL
    log.parent.mkdir(parents=True)
    log.write_text("not json at all\n", encoding="utf-8")
    assert review_verdicts.load_verdicts(tmp_path) == []


def test_load_verdicts_version_mismatch_yields_no_usable_rows(
    tmp_path: Path, monkeypatch
) -> None:
    log = tmp_path / _LOG_REL
    log.parent.mkdir(parents=True)
    row = {
        "ts": "2026-01-01T00:00:00Z",
        "lens": "security-review",
        "file_path": "f.py",
        "file_content_hash": "h",
        "outcome": "pass",
        "plugin_version": "0.0.1",
    }
    log.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(review_verdicts.plugin_version, "shipped_version", lambda: "99.0.0")
    assert review_verdicts.load_verdicts(tmp_path) == []


def test_load_verdicts_never_raises_on_a_non_object_json_line(tmp_path: Path) -> None:
    """A structurally-valid-JSON-but-not-object line (e.g. a bare list) is
    another shape of "corrupted" this reader must not choke on."""
    log = tmp_path / _LOG_REL
    log.parent.mkdir(parents=True)
    log.write_text("[1, 2, 3]\n", encoding="utf-8")
    assert review_verdicts.load_verdicts(tmp_path) == []


# ---------------------------------------------------------------------------
# Trust boundary (#2167 security review): `load_verdicts` refuses a
# git-tracked ledger outright -- a forged, PR-committed row must never
# corroborate a skip.
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_load_verdicts_rejects_a_git_tracked_ledger(tmp_path: Path) -> None:
    review_verdicts.emit_review_verdict(tmp_path, "security-review", "f.py", "h", "pass")
    _git(["init", "-q"], tmp_path)
    _git(["add", "-f", str(_LOG_REL)], tmp_path)
    assert review_verdicts.load_verdicts(tmp_path) == []


def test_load_verdicts_trusts_an_untracked_ledger_inside_a_git_repo(tmp_path: Path) -> None:
    """A git repo whose ledger is merely present -- never staged or
    committed -- is the normal, supported case (the ledger lives under
    `.claude/metrics/`, which this repo's own `.gitignore` excludes) and
    must load exactly as it would with no repo at all."""
    _git(["init", "-q"], tmp_path)
    review_verdicts.emit_review_verdict(tmp_path, "security-review", "f.py", "h", "pass")
    rows = review_verdicts.load_verdicts(tmp_path)
    assert len(rows) == 1
    assert rows[0]["file_path"] == "f.py"


def test_ledger_is_git_tracked_returns_false_when_git_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    def _boom(*_a, **_k):
        raise OSError("git not found")

    monkeypatch.setattr(review_verdicts.subprocess, "run", _boom)
    log = tmp_path / _LOG_REL
    log.parent.mkdir(parents=True)
    log.write_text("{}\n", encoding="utf-8")
    assert review_verdicts._ledger_is_git_tracked(log, tmp_path) is False


# ---------------------------------------------------------------------------
# canonical_path (#2167): the writer/reader shared path canonicalization.
# ---------------------------------------------------------------------------


def test_canonical_path_of_a_plain_relative_path_is_itself(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    assert review_verdicts.canonical_path("a.py", tmp_path) == "a.py"


def test_canonical_path_normalizes_a_dot_slash_prefix(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    assert review_verdicts.canonical_path("./a.py", tmp_path) == "a.py"


def test_canonical_path_normalizes_an_absolute_in_root_path(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    absolute = str((tmp_path / "a.py").resolve())
    assert review_verdicts.canonical_path(absolute, tmp_path) == "a.py"


def test_canonical_path_rejects_a_traversal_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    root = tmp_path / "repo"
    root.mkdir()
    rel_traversal = os.path.relpath(outside, root)
    assert review_verdicts.canonical_path(rel_traversal, root) is None


def test_canonical_path_rejects_a_path_entirely_outside_root(tmp_path: Path) -> None:
    other = tmp_path.parent / f"{tmp_path.name}-sibling"
    other.mkdir(exist_ok=True)
    assert review_verdicts.canonical_path(str(other / "evil.py"), tmp_path) is None


def test_canonical_path_does_not_require_the_file_to_exist(tmp_path: Path) -> None:
    """A verdict lookup for a file that no longer exists must still
    canonicalize -- `hash_file` is what decides "can't verify", not this
    function (mirrors `Path.resolve()`'s own no-existence-required
    contract)."""
    assert review_verdicts.canonical_path("missing.py", tmp_path) == "missing.py"


# ---------------------------------------------------------------------------
# Mechanical content-guard (acceptance-critic finding): `load_verdicts` has
# no consumer other than `scripts/verdict_scope.py` (#2167) and this
# module's own tests -- enforces the "no untracked consumer of
# review-verdicts.jsonl" boundary.
# ---------------------------------------------------------------------------

_ALLOWED_LOAD_VERDICTS_CONSUMERS = {
    _PLUGIN_DIR / "scripts" / "verdict_scope.py",
    _PLUGIN_DIR / "tests" / "scripts" / "test_verdict_scope.py",
}


def test_load_verdicts_has_no_other_consumers() -> None:
    hits: list[Path] = []
    for path in _PLUGIN_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path == _LIB_DIR / "review_verdicts.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "load_verdicts" not in text:
            continue
        hits.append(path)

    assert hits, "expected at least this test file to reference load_verdicts"
    for hit in hits:
        allowed = hit in _ALLOWED_LOAD_VERDICTS_CONSUMERS or hit.name.startswith(
            "test_review_verdicts"
        )
        assert allowed, (
            f"{hit} imports/references load_verdicts — only "
            "scripts/verdict_scope.py (#2167, the sanctioned reader) and "
            "this module's own test files may."
        )
