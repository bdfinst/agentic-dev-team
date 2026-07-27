"""Unit tests for scripts/verify_gherkin_quality_critic_isolation.py (#1465).

Covers the script's pure/structural logic — argument parsing, prerequisite
detection, fixture/prompt construction, the cross-contamination detector, and
main()'s wiring/exit-code contract — all against synthetic transcripts. None
of these tests dispatch a real `claude` CLI call or require
`ANTHROPIC_API_KEY`; `dispatch()` itself is monkeypatched wherever main() is
exercised, per this repo's existing test-scripts house style
(test_gherkin_stub_gate.py, test_run_invariants.py).
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import verify_gherkin_quality_critic_isolation as vgi

# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_defaults():
    args = vgi.parse_args([])
    assert args.model == vgi._DEFAULT_MODEL
    assert args.timeout == vgi._DEFAULT_TIMEOUT_SECONDS


def test_parse_args_overrides():
    args = vgi.parse_args(["--model", "claude-opus-4", "--timeout", "42"])
    assert args.model == "claude-opus-4"
    assert args.timeout == 42.0


def test_default_timeout_reads_env_override(monkeypatch):
    monkeypatch.setenv("VERIFY_GHERKIN_ISOLATION_TIMEOUT", "17.5")
    assert vgi._default_timeout() == 17.5


def test_default_timeout_ignores_unparseable_env(monkeypatch):
    monkeypatch.setenv("VERIFY_GHERKIN_ISOLATION_TIMEOUT", "not-a-number")
    assert vgi._default_timeout() == vgi._DEFAULT_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# check_prerequisites — fail-open detection
# ---------------------------------------------------------------------------


def test_check_prerequisites_flags_missing_cli(monkeypatch):
    monkeypatch.setattr(vgi.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    missing = vgi.check_prerequisites()
    assert any("claude` CLI" in m for m in missing)


def test_check_prerequisites_flags_missing_api_key(monkeypatch):
    monkeypatch.setattr(vgi.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    missing = vgi.check_prerequisites()
    assert any("ANTHROPIC_API_KEY" in m for m in missing)


def test_check_prerequisites_clean_when_both_present(monkeypatch):
    monkeypatch.setattr(vgi.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert vgi.check_prerequisites() == []


# ---------------------------------------------------------------------------
# build_fixture / build_prompt
# ---------------------------------------------------------------------------


def test_build_fixture_embeds_canary_and_has_no_failure_scenario():
    text = vgi.build_fixture("CANARY-XYZ")
    assert "CANARY-XYZ" in text
    assert "Feature:" in text
    # Deliberate known finding: two success-path scenarios, zero failure path.
    assert text.count("Scenario:") == 2
    assert "successfully" in text


def test_build_fixture_different_canaries_yield_different_text():
    a = vgi.build_fixture("CANARY-A")
    b = vgi.build_fixture("CANARY-B")
    assert a != b
    assert "CANARY-A" not in b
    assert "CANARY-B" not in a


def test_build_prompt_references_review_agent_skill_and_canary(tmp_path):
    feature = tmp_path / "widget_creation.feature"
    feature.write_text(vgi.build_fixture("CANARY-Q"))
    prompt = vgi.build_prompt(feature, "CANARY-Q")
    assert "/review-agent" in prompt
    assert "gherkin-quality-critic" in prompt
    assert str(feature) in prompt
    assert "CANARY-Q" in prompt


# ---------------------------------------------------------------------------
# check_cross_contamination — the core unit-testable detector
# ---------------------------------------------------------------------------


def test_no_contamination_when_transcripts_are_clean():
    violations = vgi.check_cross_contamination(
        "transcript with CANARY-A only",
        "transcript with CANARY-B only",
        "CANARY-A",
        "CANARY-B",
    )
    assert violations == []


def test_detects_b_canary_leaking_into_a_transcript():
    violations = vgi.check_cross_contamination(
        "transcript A oddly mentions CANARY-B here",
        "transcript B is clean",
        "CANARY-A",
        "CANARY-B",
    )
    assert len(violations) == 1
    assert "CANARY-B" in violations[0]
    assert "instance A's transcript" in violations[0]


def test_detects_a_canary_leaking_into_b_transcript():
    violations = vgi.check_cross_contamination(
        "transcript A is clean",
        "transcript B oddly mentions CANARY-A here",
        "CANARY-A",
        "CANARY-B",
    )
    assert len(violations) == 1
    assert "CANARY-A" in violations[0]
    assert "instance B's transcript" in violations[0]


def test_detects_bidirectional_contamination():
    violations = vgi.check_cross_contamination(
        "transcript A mentions CANARY-B",
        "transcript B mentions CANARY-A",
        "CANARY-A",
        "CANARY-B",
    )
    assert len(violations) == 2


# ---------------------------------------------------------------------------
# dispatch() — infrastructure-failure handling, no real subprocess
# ---------------------------------------------------------------------------


def test_dispatch_returns_none_on_missing_cli(monkeypatch, capsys):
    def _raise(*_a, **_k):
        raise FileNotFoundError("no such file: claude")

    monkeypatch.setattr(vgi.subprocess, "run", _raise)
    result = vgi.dispatch("prompt", "some-model", 5)
    assert result is None
    assert "SKIP" in capsys.readouterr().err


def test_dispatch_returns_none_on_timeout(monkeypatch, capsys):
    import subprocess as sp

    def _raise(*_a, **_k):
        raise sp.TimeoutExpired(cmd="claude", timeout=5)

    monkeypatch.setattr(vgi.subprocess, "run", _raise)
    result = vgi.dispatch("prompt", "some-model", 5)
    assert result is None
    assert "SKIP" in capsys.readouterr().err


def test_dispatch_returns_none_on_empty_output(monkeypatch):
    class _Proc:
        stdout = "   "
        stderr = "permission denied"
        returncode = 1

    monkeypatch.setattr(vgi.subprocess, "run", lambda *a, **k: _Proc())
    assert vgi.dispatch("prompt", "some-model", 5) is None


def test_dispatch_returns_stdout_on_success(monkeypatch):
    class _Proc:
        stdout = '{"reviewer": "gherkin-quality-critic"}'
        stderr = ""
        returncode = 0

    monkeypatch.setattr(vgi.subprocess, "run", lambda *a, **k: _Proc())
    assert vgi.dispatch("prompt", "some-model", 5) == '{"reviewer": "gherkin-quality-critic"}'


# ---------------------------------------------------------------------------
# main() — fail-open and wiring contract, dispatch() fully monkeypatched
# ---------------------------------------------------------------------------


def test_main_fails_open_when_prerequisites_missing(monkeypatch, capsys):
    monkeypatch.setattr(vgi, "check_prerequisites", lambda: ["the `claude` CLI is missing"])
    rc = vgi.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SKIP" in out
    assert "claude` CLI is missing" in out


def test_main_exits_zero_when_no_contamination(monkeypatch, capsys):
    monkeypatch.setattr(vgi, "check_prerequisites", lambda: [])
    monkeypatch.setattr(vgi, "dispatch", lambda prompt, model, timeout: "clean transcript, no canaries")
    rc = vgi.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_main_skips_when_a_dispatch_returns_none(monkeypatch, capsys):
    # One dispatch failing (infra problem) must fail OPEN — skip, not fail —
    # even though the other succeeded.
    monkeypatch.setattr(vgi, "check_prerequisites", lambda: [])
    transcripts = iter(["A-side output", None])
    monkeypatch.setattr(vgi, "dispatch", lambda prompt, model, timeout: next(transcripts))
    rc = vgi.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SKIP" in out


def test_main_exits_one_when_contamination_detected(monkeypatch, capsys):
    # Extract each dispatch's own canary from its prompt, then have the
    # SECOND dispatch's transcript leak the FIRST dispatch's canary —
    # simulating a broken/piped dispatch path — and confirm main() reports
    # it as a FAIL, not a silent pass.
    canaries: list[str] = []

    def _fake_dispatch(prompt, model, timeout):
        canary = prompt.split("Context marker for this dispatch only: ")[1].splitlines()[0].strip()
        canaries.append(canary)
        if len(canaries) == 1:
            return "clean transcript A"
        return f"transcript B unexpectedly mentions {canaries[0]}"

    monkeypatch.setattr(vgi, "check_prerequisites", lambda: [])
    monkeypatch.setattr(vgi, "dispatch", _fake_dispatch)
    rc = vgi.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    assert "cross-contamination detected" in out


def test_main_skips_when_first_dispatch_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(vgi, "check_prerequisites", lambda: [])
    monkeypatch.setattr(vgi, "dispatch", lambda prompt, model, timeout: None)
    rc = vgi.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SKIP" in out
