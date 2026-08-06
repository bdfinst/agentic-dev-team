"""Unit tests for hooks/pre_tool_guard.py (#602).

Behavioural coverage of `evaluate()` — one assertion per code path. The
parity harness holds the bash byte-for-byte equivalence line separately.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_TESTS_LIB = _PLUGIN_DIR / "tests" / "lib"

for _p in (_PLUGIN_DIR / "hooks", _TESTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pre_tool_guard
from hermetic import hermetic_git_env  # type: ignore[import-not-found]


@pytest.fixture(autouse=True)
def _no_boundary_events(monkeypatch):
    """evaluate() defaults cwd="." — without this, emit_boundary_event
    (#859) would resolve metrics/ against the test process's real OS cwd.
    Boundary-event emission itself is covered end-to-end in
    tests/hooks/test_boundary_events.py.
    """
    monkeypatch.setattr(pre_tool_guard, "emit_boundary_event", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# _extract_file_path
# ---------------------------------------------------------------------------


def test_extract_file_path_prefers_file_path():
    raw = '{"tool_input":{"file_path":"a.py","path":"b.py"}}'
    assert pre_tool_guard._extract_file_path(raw) == "a.py"


def test_extract_file_path_falls_back_to_path():
    raw = '{"tool_input":{"path":"b.py"}}'
    assert pre_tool_guard._extract_file_path(raw) == "b.py"


def test_extract_file_path_empty_when_neither():
    assert pre_tool_guard._extract_file_path('{"tool_input":{}}') == ""


def test_extract_file_path_empty_when_malformed_json():
    assert pre_tool_guard._extract_file_path("not-json") == ""


def test_extract_file_path_empty_when_top_level_not_a_dict():
    assert pre_tool_guard._extract_file_path(json.dumps(["a.py"])) == ""


def test_extract_file_path_empty_when_tool_input_not_a_dict():
    assert pre_tool_guard._extract_file_path(json.dumps({"tool_input": "a.py"})) == ""


def test_extract_file_path_empty_when_empty_string_field():
    raw = '{"tool_input":{"file_path":""}}'
    assert pre_tool_guard._extract_file_path(raw) == ""


# ---------------------------------------------------------------------------
# _matches_any — case-sensitive fnmatch (subjects are lowercased upstream)
# ---------------------------------------------------------------------------


def test_matches_any_glob():
    assert pre_tool_guard._matches_any("api.token", [".env", "*.token"]) is True


def test_matches_any_no_match():
    assert pre_tool_guard._matches_any("readme.md", [".env", "*.key"]) is False


def test_matches_any_skips_empty_patterns():
    assert pre_tool_guard._matches_any(".env", ["", ".env"]) is True


# ---------------------------------------------------------------------------
# _load_guards
# ---------------------------------------------------------------------------


def test_load_guards_returns_defaults_when_file_absent(tmp_path):
    blocked, warn = pre_tool_guard._load_guards(tmp_path / "missing.json")
    assert ".env" in blocked
    assert ".claude/settings.json" in warn


def test_load_guards_reads_custom_patterns(tmp_path):
    guards = tmp_path / "guards.json"
    guards.write_text(
        json.dumps({"blocked_paths": ["*.foo"], "warn_paths": ["config.yml"]})
    )
    blocked, warn = pre_tool_guard._load_guards(guards)
    assert blocked == ["*.foo"]
    assert warn == ["config.yml"]


def test_load_guards_falls_back_when_malformed(tmp_path):
    (tmp_path / "guards.json").write_text("{not-json")
    blocked, _warn = pre_tool_guard._load_guards(tmp_path / "guards.json")
    assert ".env" in blocked


def test_load_freeze_returns_none_when_active_field_absent(tmp_path):
    freeze = tmp_path / "freeze-state.json"
    freeze.write_text(json.dumps({"allowed_patterns": ["*.md"]}))
    assert pre_tool_guard._load_freeze(freeze) is None


def test_load_freeze_falls_back_to_empty_when_allowed_patterns_not_a_list(tmp_path):
    """Regression: a truthy non-list `allowed_patterns` must not crash —
    freeze stays active with zero allowed patterns rather than raising."""
    freeze = tmp_path / "freeze-state.json"
    freeze.write_text(json.dumps({"active": True, "allowed_patterns": True}))
    assert pre_tool_guard._load_freeze(freeze) == []


def test_load_freeze_returns_none_when_top_level_not_a_dict(tmp_path):
    freeze = tmp_path / "freeze-state.json"
    freeze.write_text(json.dumps(["active", True]))
    assert pre_tool_guard._load_freeze(freeze) is None


def test_load_guards_falls_back_when_top_level_not_a_dict(tmp_path):
    guards = tmp_path / "guards.json"
    guards.write_text(json.dumps(["blocked_paths", "*.foo"]))
    blocked, warn = pre_tool_guard._load_guards(guards)
    assert ".env" in blocked
    assert ".claude/settings.json" in warn


def test_load_guards_falls_back_when_blocked_paths_not_a_list(tmp_path):
    """Regression: a truthy non-list (e.g. `true`) must not crash the
    comprehension — `data.get(...) or []` doesn't help when the value
    itself is truthy but not iterable-as-expected."""
    guards = tmp_path / "guards.json"
    guards.write_text(json.dumps({"blocked_paths": True, "warn_paths": 5}))
    blocked, warn = pre_tool_guard._load_guards(guards)
    assert ".env" in blocked
    assert ".claude/settings.json" in warn


# ---------------------------------------------------------------------------
# evaluate() — decision matrix
# ---------------------------------------------------------------------------


@pytest.fixture
def default_guards(tmp_path):
    """Return (guards_path, freeze_path) where guards.json holds defaults."""
    guards = tmp_path / "guards.json"
    guards.write_text(
        json.dumps(
            {
                "blocked_paths": pre_tool_guard._DEFAULT_BLOCKED,
                "warn_paths": pre_tool_guard._DEFAULT_WARN,
            }
        )
    )
    return guards, tmp_path / "freeze-state.json"


def _paths(guards, freeze, repo_root=None):
    """Build a `GuardPaths` for `evaluate()`'s `paths=` keyword argument."""
    return pre_tool_guard.GuardPaths(guards, freeze, repo_root)


def test_evaluate_blocks_env(default_guards):
    guards, freeze = default_guards
    code, lines = pre_tool_guard.evaluate(".env", paths=_paths(guards, freeze))
    assert code == 2
    assert lines[0] == "BLOCKED: Write to '.env' is not allowed."


def test_evaluate_blocks_dotenv_variant(default_guards):
    guards, freeze = default_guards
    code, _ = pre_tool_guard.evaluate(".env.production", paths=_paths(guards, freeze))
    assert code == 2


def test_evaluate_blocks_key_file(default_guards):
    guards, freeze = default_guards
    code, _ = pre_tool_guard.evaluate("secrets/api.key", paths=_paths(guards, freeze))
    assert code == 2


def test_evaluate_case_insensitive_block(default_guards):
    guards, freeze = default_guards
    code, _ = pre_tool_guard.evaluate("SECRET_STORE.json", paths=_paths(guards, freeze))
    assert code == 2


def test_evaluate_warns_settings(default_guards):
    guards, freeze = default_guards
    code, lines = pre_tool_guard.evaluate(
        ".claude/settings.json", paths=_paths(guards, freeze)
    )
    assert code == 0
    assert lines[0].startswith("WARNING:")


def test_evaluate_allows_regular_file(default_guards):
    guards, freeze = default_guards
    code, lines = pre_tool_guard.evaluate("src/app.py", paths=_paths(guards, freeze))
    assert code == 0
    assert lines == []


def test_evaluate_empty_path_is_silent_pass(default_guards):
    guards, freeze = default_guards
    assert pre_tool_guard.evaluate("", paths=_paths(guards, freeze)) == (0, [])


# ---------------------------------------------------------------------------
# Freeze mode
# ---------------------------------------------------------------------------


def _write_freeze(freeze_path: Path, active: bool, allowed):
    freeze_path.write_text(json.dumps({"active": active, "allowed_patterns": allowed}))


def test_freeze_blocks_paths_outside_allowed(tmp_path):
    guards = tmp_path / "guards.json"
    freeze = tmp_path / "freeze-state.json"
    _write_freeze(freeze, True, ["src/*.py"])
    code, lines = pre_tool_guard.evaluate("tests/foo.py", paths=_paths(guards, freeze))
    assert code == 2
    assert lines[0].startswith("BLOCKED: Freeze mode is active.")


def test_freeze_allows_paths_matching_pattern(tmp_path):
    guards = tmp_path / "guards.json"
    freeze = tmp_path / "freeze-state.json"
    _write_freeze(freeze, True, ["src/app.py"])
    code, lines = pre_tool_guard.evaluate("src/app.py", paths=_paths(guards, freeze))
    # Falls through to normal guards (default), which pass this path.
    assert code == 0
    assert lines == []


def test_freeze_inactive_does_not_gate(tmp_path):
    guards = tmp_path / "guards.json"
    freeze = tmp_path / "freeze-state.json"
    _write_freeze(freeze, False, ["src/*.py"])
    code, _ = pre_tool_guard.evaluate("tests/foo.py", paths=_paths(guards, freeze))
    assert code == 0


# ---------------------------------------------------------------------------
# Freeze allowlist matching against an ABSOLUTE file_path (#1904 item 14) —
# a real session always reports file_path as absolute; a repo-relative
# pattern can only ever match once file_path is relativized against the
# freeze-scoped repo root.
# ---------------------------------------------------------------------------


def test_freeze_allows_absolute_file_path_matching_relative_pattern(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    guards = repo / "guards.json"
    freeze = repo / "freeze-state.json"
    _write_freeze(freeze, True, ["src/app.py"])
    absolute_file_path = str((repo / "src" / "app.py").resolve())

    code, lines = pre_tool_guard.evaluate(
        absolute_file_path, cwd=str(repo), paths=_paths(guards, freeze, repo)
    )
    assert code == 0
    assert lines == []


def test_freeze_blocks_absolute_file_path_outside_allowed_pattern(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    guards = repo / "guards.json"
    freeze = repo / "freeze-state.json"
    _write_freeze(freeze, True, ["src/app.py"])
    absolute_file_path = str((repo / "tests" / "foo.py").resolve())

    code, lines = pre_tool_guard.evaluate(
        absolute_file_path, cwd=str(repo), paths=_paths(guards, freeze, repo)
    )
    assert code == 2
    assert lines[0].startswith("BLOCKED: Freeze mode is active.")


def test_freeze_without_repo_root_still_matches_relative_subject_as_before(tmp_path):
    """Backward compatibility: a caller that omits `repo_root` (every
    pre-#1904 call site) keeps matching `file_path` as-is — no relative-path
    behavior change for callers that already pass a repo-relative subject."""
    guards = tmp_path / "guards.json"
    freeze = tmp_path / "freeze-state.json"
    _write_freeze(freeze, True, ["src/app.py"])
    code, lines = pre_tool_guard.evaluate("src/app.py", paths=_paths(guards, freeze))
    assert code == 0
    assert lines == []


# ---------------------------------------------------------------------------
# Freeze scope must not apply to a file_path outside the freeze-scoped
# repo entirely (#1904 item 7) — the inverse, under-blocking direction: a
# same-shaped relative path in a DIFFERENT repo must not be treated as
# covered by this repo's allowlist.
# ---------------------------------------------------------------------------


def test_freeze_does_not_gate_file_path_outside_repo_root(tmp_path):
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    guards = repo_a / "guards.json"
    freeze = repo_a / "freeze-state.json"
    _write_freeze(freeze, True, ["docs/readme.md"])
    # Identical relative shape to the allowed pattern, but rooted in repo B.
    absolute_file_path = str((repo_b / "docs" / "readme.md").resolve())

    code, lines = pre_tool_guard.evaluate(
        absolute_file_path, cwd=str(repo_a), paths=_paths(guards, freeze, repo_a)
    )
    # Freeze's allowlist never governs this write — it falls through to the
    # ordinary sensitive-path/warn checks, which pass a plain .md silently.
    assert code == 0
    assert lines == []


def test_freeze_does_not_wrongly_allow_cross_repo_file_either(tmp_path):
    """The cross-repo exemption is symmetric: a file_path outside the
    freeze-scoped repo is neither blocked NOR allowed by that repo's
    allowlist — it is simply outside freeze's scope. A pattern that would
    NOT match is equally irrelevant here."""
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    guards = repo_a / "guards.json"
    freeze = repo_a / "freeze-state.json"
    _write_freeze(freeze, True, ["src/*.py"])
    absolute_file_path = str((repo_b / "docs" / "readme.md").resolve())

    code, lines = pre_tool_guard.evaluate(
        absolute_file_path, cwd=str(repo_a), paths=_paths(guards, freeze, repo_a)
    )
    assert code == 0
    assert lines == []


# ---------------------------------------------------------------------------
# Freeze-scope symlink escape: a candidate nominally INSIDE the frozen repo
# (as written, unresolved) that resolves OUTSIDE it via a symlink must be
# BLOCKED, not silently allowed by falling through to the ordinary
# sensitive-path/warn checks.
# ---------------------------------------------------------------------------


def test_freeze_blocks_symlink_escape_out_of_repo_root(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    guards = repo / "guards.json"
    freeze = repo / "freeze-state.json"
    _write_freeze(freeze, True, ["src/*.py"])
    (repo / "tests").symlink_to(outside, target_is_directory=True)
    written_path = str(repo / "tests" / "evil.py")

    code, lines = pre_tool_guard.evaluate(
        written_path, cwd=str(repo), paths=_paths(guards, freeze, repo)
    )
    assert code == 2
    assert lines[0].startswith("BLOCKED: Freeze mode is active.")


def test_freeze_symlink_escape_not_confused_with_genuine_cross_repo_path(tmp_path):
    """A path that resolves outside `repo_root` WITHOUT ever having been
    written/joined as if inside it (the ordinary cross-repo case) must
    stay unblocked — only a path whose unresolved form was inside
    `repo_root` counts as a symlink escape."""
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    guards = repo_a / "guards.json"
    freeze = repo_a / "freeze-state.json"
    _write_freeze(freeze, True, ["src/*.py"])
    absolute_file_path = str((repo_b / "docs" / "readme.md").resolve())

    code, lines = pre_tool_guard.evaluate(
        absolute_file_path, cwd=str(repo_a), paths=_paths(guards, freeze, repo_a)
    )
    assert code == 0
    assert lines == []


# ---------------------------------------------------------------------------
# _cheap_freeze_inactive / main()'s cheap-stat fast path (#1904 item 11) —
# avoids the git-rev-parse-based resolution on every Write/Edit when it can
# prove freeze is inactive from a plain filesystem stat alone.
# ---------------------------------------------------------------------------


def test_cheap_freeze_inactive_true_at_repo_root_with_no_freeze_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    assert pre_tool_guard._cheap_freeze_inactive(str(repo)) is True


def test_cheap_freeze_inactive_false_when_freeze_file_exists(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    freeze_dir = repo / ".claude" / "hooks"
    freeze_dir.mkdir(parents=True)
    (freeze_dir / "freeze-state.json").write_text("{}")
    assert pre_tool_guard._cheap_freeze_inactive(str(repo)) is False


def test_cheap_freeze_inactive_false_when_cwd_is_not_repo_root(tmp_path):
    # No .git directly under cwd — ambiguous (the file could exist at an
    # ancestor this check never looks at) — must fall through.
    sub = tmp_path / "sub"
    sub.mkdir()
    assert pre_tool_guard._cheap_freeze_inactive(str(sub)) is False


def test_main_skips_git_subprocess_when_repo_root_has_no_freeze_file(
    monkeypatch, tmp_path
):
    import io

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    calls = []
    monkeypatch.setattr(
        pre_tool_guard.artifact_paths,
        "project_root",
        lambda *a, **k: calls.append((a, k)) or repo,
    )
    payload = json.dumps({"tool_input": {"file_path": "src/app.py"}, "cwd": str(repo)})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    assert pre_tool_guard.main() == 0
    assert calls == []


def test_main_falls_through_to_git_resolution_when_cwd_is_a_subdirectory(
    monkeypatch, tmp_path
):
    import io

    repo = tmp_path / "repo"
    sub = repo / "sub"
    sub.mkdir(parents=True)
    (repo / ".git").mkdir()
    calls = []

    def _fake_project_root(*a, **k):
        calls.append((a, k))
        return repo

    monkeypatch.setattr(pre_tool_guard.artifact_paths, "project_root", _fake_project_root)
    payload = json.dumps({"tool_input": {"file_path": "src/app.py"}, "cwd": str(sub)})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    assert pre_tool_guard.main() == 0
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Freeze-state path is scoped per invoking repo, not the hook's own
# script_dir (#1890) — main() resolves it via artifact_paths.resolve_file(),
# keyed off cwd, so two concurrent sessions/worktrees never share one file.
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> dict:
    env = hermetic_git_env(home=path)
    subprocess.run(["git", "init", "-q"], cwd=path, env=env, check=True)
    return env


def test_main_resolves_freeze_state_under_the_repo_root(tmp_path):
    """The path main() computes for a given cwd lands under that repo's own
    `.claude/hooks/`, not relative to pre_tool_guard.py's own directory."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    freeze_path = pre_tool_guard.artifact_paths.resolve_file(
        "hooks", "freeze-state.json", root=repo, migrate=False
    )

    assert freeze_path == repo.resolve() / ".claude" / "hooks" / "freeze-state.json"
    hook_own_dir = Path(pre_tool_guard.__file__).resolve().parent
    assert hook_own_dir not in freeze_path.parents


def test_main_does_not_crash_on_a_non_string_cwd(monkeypatch):
    """Closing-pass regression: main() must not let an unvalidated,
    non-string `cwd` (or one containing a NUL byte) reach
    artifact_paths.resolve_file()/project_root(), which would raise and
    let the sensitive-path guard fail open silently instead of blocking."""
    import io

    payload = json.dumps({"tool_input": {"file_path": ".env"}, "cwd": 123})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert pre_tool_guard.main() == 2


def test_freeze_in_one_repo_does_not_gate_a_different_concurrent_repo(tmp_path):
    """Two concurrent 'sessions' (two separate repo roots): activating
    /freeze in repo A's resolved path must not affect evaluate() for repo B,
    even though both hash to the identical bare filename."""
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    _init_repo(repo_a)
    _init_repo(repo_b)

    freeze_a = pre_tool_guard.artifact_paths.resolve_file(
        "hooks", "freeze-state.json", root=repo_a, migrate=False
    )
    freeze_b = pre_tool_guard.artifact_paths.resolve_file(
        "hooks", "freeze-state.json", root=repo_b, migrate=False
    )
    assert freeze_a != freeze_b

    freeze_a.parent.mkdir(parents=True, exist_ok=True)
    _write_freeze(freeze_a, True, ["src/*.py"])
    assert not freeze_b.exists()

    guards_a = repo_a / "guards.json"
    guards_b = repo_b / "guards.json"

    # Repo A's own freeze is genuinely enforced against its own resolved path.
    code, lines = pre_tool_guard.evaluate(
        "tests/foo.py", paths=_paths(guards_a, freeze_a)
    )
    assert code == 2
    assert lines[0].startswith("BLOCKED: Freeze mode is active.")

    # Repo B — a different, concurrently-running session — sees no freeze at
    # all: repo A's activation never leaks into repo B's evaluation.
    code, lines = pre_tool_guard.evaluate(
        "tests/foo.py", paths=_paths(guards_b, freeze_b)
    )
    assert code == 0
    assert lines == []
