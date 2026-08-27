"""Unit tests for hooks/session_learning_trigger.py (#603).

Behavioural coverage of the state file helpers and `main()` decision paths.
Parity vs bash lives in `tests/hooks/parity/test_session_learning_trigger_parity.py`.
"""

from __future__ import annotations

import io
import json
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import session_learning_trigger as slt

# ---------------------------------------------------------------------------
# _load_counter
# ---------------------------------------------------------------------------


def test_load_counter_absent_returns_zero(tmp_path):
    assert slt._load_counter(tmp_path / "missing.json") == 0


def test_load_counter_reads_int(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"counter":7}')
    assert slt._load_counter(p) == 7


def test_load_counter_recovers_from_corrupt_json(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("this is not json")
    assert slt._load_counter(p) == 0


def test_load_counter_recovers_from_non_integer(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"counter":"seven"}')
    assert slt._load_counter(p) == 0


def test_load_counter_accepts_numeric_string(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"counter":"3"}')
    assert slt._load_counter(p) == 3


# ---------------------------------------------------------------------------
# _write_state
# ---------------------------------------------------------------------------


def test_write_state_writes_json_atomically(tmp_path):
    state = tmp_path / "metrics" / "learning-loop-state.json"
    slt._write_state(state, 5)
    assert state.read_text().rstrip() == '{"counter":5}'


def test_write_state_trailing_newline_matches_bash(tmp_path):
    state = tmp_path / "metrics" / "learning-loop-state.json"
    slt._write_state(state, 1)
    assert state.read_text().endswith("\n")


def test_write_state_leaves_no_temp_files_on_success(tmp_path):
    state = tmp_path / "metrics" / "learning-loop-state.json"
    slt._write_state(state, 2)
    leftovers = list(state.parent.glob(".learning-loop-state-*"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# shell_quote — used to build the fire-and-forget subprocess command
# ---------------------------------------------------------------------------


def test_shell_quote_wraps_and_escapes():
    assert slt.shell_quote("plain") == "'plain'"
    assert slt.shell_quote("has'quote") == "'has'\"'\"'quote'"


# ---------------------------------------------------------------------------
# main() decision paths — mock the dispatch so we don't fork a child
# ---------------------------------------------------------------------------


def _feed_stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_main_consent_off_exits_zero(monkeypatch, tmp_path):
    monkeypatch.delenv("DEV_TEAM_AUTO_REVIEW", raising=False)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '"}')
    assert slt.main() == 0
    assert not (tmp_path / ".claude" / "metrics" / "learning-loop-state.json").exists()


def test_main_malformed_json_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    _feed_stdin(monkeypatch, "not-json")
    assert slt.main() == 0
    # No state file created since parse failed early.
    assert not (tmp_path / ".claude" / "metrics" / "learning-loop-state.json").exists()


def test_main_increments_counter(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "5")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(slt.telemetry_consent, "is_enabled", lambda: True)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '","session_id":"s1"}')
    # Prevent actual background dispatch attempt (irrelevant for counter step).
    monkeypatch.setattr(slt, "_dispatch_background_analysis", lambda *_a, **_k: None)
    assert slt.main() == 0
    state = tmp_path / ".claude" / "metrics" / "learning-loop-state.json"
    assert json.loads(state.read_text()) == {"counter": 1}


def test_main_dispatches_and_resets_counter_at_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "2")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(slt.telemetry_consent, "is_enabled", lambda: True)
    (tmp_path / ".claude" / "metrics").mkdir(parents=True)
    (tmp_path / ".claude" / "metrics" / "learning-loop-state.json").write_text('{"counter":1}')

    dispatched = []

    def fake_dispatch(cwd, session_id, hook_dir):
        dispatched.append((str(cwd), session_id, str(hook_dir)))

    monkeypatch.setattr(slt, "_dispatch_background_analysis", fake_dispatch)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '","session_id":"sX"}')

    assert slt.main() == 0
    assert dispatched, "dispatch should fire at threshold"
    state = tmp_path / ".claude" / "metrics" / "learning-loop-state.json"
    # Counter reset to 0 after dispatch
    assert json.loads(state.read_text()) == {"counter": 0}


def test_main_falls_back_to_pwd_when_cwd_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(slt.telemetry_consent, "is_enabled", lambda: True)
    monkeypatch.setattr(slt, "_dispatch_background_analysis", lambda *_a, **_k: None)
    _feed_stdin(monkeypatch, "{}")
    assert slt.main() == 0
    # State file created under PWD.
    state = tmp_path / ".claude" / "metrics" / "learning-loop-state.json"
    assert state.exists()


def test_main_invalid_threshold_env_uses_default(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "not-a-number")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(slt.telemetry_consent, "is_enabled", lambda: True)
    monkeypatch.setattr(slt, "_dispatch_background_analysis", lambda *_a, **_k: None)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '"}')
    assert slt.main() == 0
    # With default threshold=5, counter=1 after first invocation.
    state = tmp_path / ".claude" / "metrics" / "learning-loop-state.json"
    assert json.loads(state.read_text()) == {"counter": 1}


class TestTelemetryConsent:
    def test_no_consent_no_state_write_even_with_auto_review_on(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(slt.telemetry_consent, "is_enabled", lambda: False)
        dispatched = []
        monkeypatch.setattr(
            slt, "_dispatch_background_analysis", lambda *a, **k: dispatched.append(1)
        )
        _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '"}')
        assert slt.main() == 0
        assert not (tmp_path / ".claude" / "metrics" / "learning-loop-state.json").exists()
        assert not dispatched

    def test_consent_enabled_but_per_writer_opt_out_still_suppresses(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("DEV_TEAM_AUTO_REVIEW", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(slt.telemetry_consent, "is_enabled", lambda: True)
        _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '"}')
        assert slt.main() == 0
        assert not (tmp_path / ".claude" / "metrics" / "learning-loop-state.json").exists()

    def test_consent_enabled_and_opted_in_writes_state(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
        monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "5")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(slt.telemetry_consent, "is_enabled", lambda: True)
        _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '"}')
        assert slt.main() == 0
        state = tmp_path / ".claude" / "metrics" / "learning-loop-state.json"
        assert json.loads(state.read_text()) == {"counter": 1}


# ---------------------------------------------------------------------------
# _resolve_session_report / _dispatch_background_analysis (#1649, #2047)
# ---------------------------------------------------------------------------


def test_resolve_session_report_targets_shipped_plugin_scripts_dir():
    """hook_dir is plugins/dev-team/hooks; scripts/session_report.py is a
    sibling one level up (hooks -> dev-team -> scripts), unlike the
    pre-#2047 repo-root scripts/session_extract.py target, which needed
    three levels (hooks -> dev-team -> plugins -> repo root)."""
    hook_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
    resolved = slt._resolve_session_report(hook_dir)
    assert resolved == (
        _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "session_report.py"
    ).resolve()


def test_resolve_session_report_finds_the_real_file_in_this_checkout():
    """Unlike the pre-#2047 session_extract.py target (monorepo-only,
    absent on every downstream install), session_report.py SHIPS -- so this
    must resolve to a real file both in this dev checkout and, per #2047,
    on any install."""
    hook_dir = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
    assert slt._resolve_session_report(hook_dir).is_file()


def _patch_dispatch_popen(monkeypatch, popen_calls):
    """Intercept only the `["sh", "-c", ...]` Popen call `_dispatch_background_
    analysis` makes, delegating everything else to the real `subprocess.Popen`.

    `slt.subprocess` is the same module object `artifact_paths.py` imports as
    `subprocess` — Python modules are singletons — so a blanket
    `monkeypatch.setattr(slt.subprocess, "Popen", ...)` also replaces the
    `Popen` that `artifact_paths.resolve_file()`'s own unrelated subprocess
    call (used to locate the repo root) runs through, breaking it with no
    connection to what this test is actually exercising. Selecting on the
    call shape keeps the patch scoped to the one call under test."""
    real_popen = slt.subprocess.Popen

    class _NoOpProcess:
        pass

    def fake_popen(args, *rest, **kwargs):
        if isinstance(args, list) and args[:2] == ["sh", "-c"]:
            popen_calls.append((args, kwargs))
            return _NoOpProcess()
        return real_popen(args, *rest, **kwargs)

    monkeypatch.setattr(slt.subprocess, "Popen", fake_popen)


def test_dispatch_skips_entirely_when_session_report_is_absent(monkeypatch, tmp_path):
    """A broken/partial install (session_report.py missing) must skip
    cleanly rather than compose a shell command guaranteed to fail -- the
    defensive check kept from #1649, even though #2047 means the normal
    case is now for the target to be present on every install."""
    fake_hook_dir = tmp_path / "plugins" / "dev-team" / "hooks"
    fake_hook_dir.mkdir(parents=True)
    popen_calls = []
    monkeypatch.setattr(
        slt.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k))
    )
    slt._dispatch_background_analysis(tmp_path, "sess-1", fake_hook_dir)
    assert popen_calls == [], "no subprocess should be spawned when the target script is absent"


def test_dispatch_spawns_when_session_report_is_present(monkeypatch, tmp_path):
    """The normal case per #2047: session_report.py ships alongside the
    hook, so dispatch happens on every install, not just a monorepo dev
    checkout."""
    fake_hook_dir = tmp_path / "plugins" / "dev-team" / "hooks"
    fake_hook_dir.mkdir(parents=True)
    fake_scripts = tmp_path / "plugins" / "dev-team" / "scripts"
    fake_scripts.mkdir(parents=True)
    (fake_scripts / "session_report.py").write_text("# fake\n")

    popen_calls = []
    _patch_dispatch_popen(monkeypatch, popen_calls)
    slt._dispatch_background_analysis(tmp_path, "sess-1", fake_hook_dir)
    assert len(popen_calls) == 1
    argv = popen_calls[0][0]
    assert argv[:2] == ["sh", "-c"]
    assert "--profile maintainer" in argv[2]


def test_dispatch_logs_session_report_stderr_instead_of_discarding_it(
    monkeypatch, tmp_path
):
    """#1649: a genuine failure inside this checkout must leave evidence
    (metrics_dir/session-learning-errors.log), not vanish behind a bare
    `|| true`."""
    fake_hook_dir = tmp_path / "plugins" / "dev-team" / "hooks"
    fake_hook_dir.mkdir(parents=True)
    fake_scripts = tmp_path / "plugins" / "dev-team" / "scripts"
    fake_scripts.mkdir(parents=True)
    (fake_scripts / "session_report.py").write_text("# fake\n")

    popen_calls = []
    _patch_dispatch_popen(monkeypatch, popen_calls)
    slt._dispatch_background_analysis(tmp_path, "sess-1", fake_hook_dir)

    shell_body = popen_calls[0][0][2]
    assert "/dev/null 2>&1 || true" not in shell_body.split(";")[0], (
        "session_report's stderr must not be discarded to /dev/null"
    )
    assert "session-learning-errors.log" in shell_body
    assert "2>>" in shell_body, "must append, not truncate, across repeated dispatches"
