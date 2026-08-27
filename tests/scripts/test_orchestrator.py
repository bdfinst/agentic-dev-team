"""Pytest async tests for plugins/dev-team/scripts/orchestrator.py — Slice 6.

Tests classification, fast-path routing, phase state persistence,
--resume skip logic, persona dispatch concurrency, and wave barrier.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure plugins/dev-team/scripts/ is on the path so we can import orchestrator
SCRIPTS = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import orchestrator as orch

# ---------------------------------------------------------------------------
# Step 1.1 — DEFAULT_PERSONAS / CODE_REVIEW_PANEL / JSON_CONTRACT_PERSONAS
# ---------------------------------------------------------------------------


def test_default_personas_is_exactly_the_five_plan_review_critics():
    """DEFAULT_PERSONAS must equal exactly the five real plan-review-* agent
    names, and must not contain the stale, nonexistent persona names."""
    assert orch.DEFAULT_PERSONAS == [
        "plan-review-acceptance",
        "plan-review-design",
        "plan-review-ux",
        "plan-review-strategic",
        "plan-review-parallelization",
    ]
    assert "acceptance-test-critic" not in orch.DEFAULT_PERSONAS
    assert "design-architecture-critic" not in orch.DEFAULT_PERSONAS


def test_code_review_panel_is_the_named_fixed_trio():
    """CODE_REVIEW_PANEL must equal exactly the language-agnostic
    always-run trio per docs/team-structure.md's review-dispatch fan-out."""
    assert orch.CODE_REVIEW_PANEL == [
        "doc-review",
        "arch-review",
        "token-efficiency-review",
    ]


def test_json_contract_personas_is_exactly_the_union():
    """JSON_CONTRACT_PERSONAS must be exactly DEFAULT_PERSONAS + CODE_REVIEW_PANEL,
    in that order, with no other members."""
    assert orch.JSON_CONTRACT_PERSONAS == orch.DEFAULT_PERSONAS + orch.CODE_REVIEW_PANEL
    assert orch.JSON_CONTRACT_PERSONAS == [
        "plan-review-acceptance",
        "plan-review-design",
        "plan-review-ux",
        "plan-review-strategic",
        "plan-review-parallelization",
        "doc-review",
        "arch-review",
        "token-efficiency-review",
    ]


# ---------------------------------------------------------------------------
# Step 1.1 — _touches_security() keyword heuristic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword",
    [
        "auth",
        "secret",
        "crypto",
        "password",
        "token",
        "credential",
        "encrypt",
    ],
)
def test_touches_security_matches_each_keyword_individually(keyword):
    """Each keyword in SECURITY_KEYWORDS must trigger a True result on its own."""
    assert orch._touches_security(f"please rotate the {keyword} now") is True


def test_touches_security_returns_false_when_no_keyword_present():
    assert orch._touches_security("fix a typo in the README") is False


def test_security_keywords_is_exactly_the_normative_seven():
    """SECURITY_KEYWORDS is _touches_security's one normative source
    (AC #2) — pin its exact contents so an added/removed keyword fails
    this test rather than silently widening or narrowing the heuristic."""
    assert orch.SECURITY_KEYWORDS == (
        "auth",
        "secret",
        "crypto",
        "password",
        "token",
        "credential",
        "encrypt",
    )


def test_research_personas_is_exactly_the_three_always_on_trio():
    """RESEARCH_PERSONAS must equal exactly the three real always-on
    Research-phase agent names, matching DEFAULT_PERSONAS/CODE_REVIEW_PANEL's
    own exact-equality pinning pattern."""
    assert orch.RESEARCH_PERSONAS == ("codebase-recon", "architect", "data-flow-tracer")


def test_plan_core_personas_is_exactly_the_three_always_on_trio():
    """PLAN_CORE_PERSONAS must equal exactly the three real Plan-phase core
    agent names, in the declared order, matching RESEARCH_PERSONAS's own
    exact-equality pinning pattern."""
    assert orch.PLAN_CORE_PERSONAS == ("product-manager", "architect", "qa-engineer")


def test_implement_persona_is_exactly_software_engineer():
    """SOFTWARE_ENGINEER_PERSONA must equal exactly "software-engineer", matching
    SECURITY_ENGINEER_PERSONA's own exact-equality pinning pattern."""
    assert orch.SOFTWARE_ENGINEER_PERSONA == "software-engineer"


def test_tech_writer_persona_is_exactly_tech_writer():
    """TECH_WRITER_PERSONA must equal exactly "tech-writer"."""
    assert orch.TECH_WRITER_PERSONA == "tech-writer"


def test_classify_timeout_is_exactly_30_seconds():
    """CLASSIFY_TIMEOUT_S must equal exactly 30 (follow-up #1716) — an
    accidental edit to this constant should fail this test directly instead
    of only surfacing as a flaky/slow-CLI symptom in classify()'s own
    subprocess.run call."""
    assert orch.CLASSIFY_TIMEOUT_S == 30


def test_persona_dispatch_timeout_is_exactly_60_seconds():
    """PERSONA_DISPATCH_TIMEOUT_S must equal exactly 60 (follow-up #1716),
    matching CLASSIFY_TIMEOUT_S's own pinning test above."""
    assert orch.PERSONA_DISPATCH_TIMEOUT_S == 60


def test_implement_wave_slices_is_exactly_the_single_synthetic_slice():
    """IMPLEMENT_WAVE_SLICES must equal exactly ("implement-1",) — the one
    normative definition of this persisted, operator-facing slice name,
    matching the persona constants' own exact-equality pinning pattern."""
    assert orch.IMPLEMENT_WAVE_SLICES == ("implement-1",)


@pytest.mark.parametrize(
    "persona",
    [
        *orch.RESEARCH_PERSONAS,
        *orch.PLAN_CORE_PERSONAS,
        *orch.DEFAULT_PERSONAS,
        *orch.CODE_REVIEW_PANEL,
        orch.SECURITY_ENGINEER_PERSONA,
        orch.SOFTWARE_ENGINEER_PERSONA,
        orch.TECH_WRITER_PERSONA,
    ],
)
def test_every_dispatchable_persona_resolves_to_a_real_agent(persona):
    """Every persona name orchestrator.py can pass to `claude -p --agent
    <name>` must resolve to a shipped agent definition — the exact class of
    defect DEFAULT_PERSONAS previously shipped (see
    test_default_personas_is_exactly_the_five_plan_review_critics), now
    guarded mechanically instead of only by a literal-list assertion that
    can't catch a persona ceasing to exist."""
    agents_dir = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "agents"
    assert (agents_dir / f"{persona}.md").exists(), (
        f"{persona} has no plugins/dev-team/agents/{persona}.md"
    )


def test_touches_security_is_case_insensitive():
    """"AUTHENTICATE" must still match the lowercase "auth" keyword."""
    assert orch._touches_security("AUTHENTICATE the user via OAuth") is True


def test_touches_security_returns_false_for_empty_string():
    assert orch._touches_security("") is False


def test_touches_security_accepts_substring_false_positive_as_intentional():
    """"cryptocurrency" contains the "crypto" substring, so this heuristic
    returns True even though the request has nothing to do with security.
    This is documented, accepted heuristic behavior (plan Risks section),
    not a bug — Step 1.1 is a keyword/substring check, not a precise
    classifier."""
    assert orch._touches_security("track the cryptocurrency market") is True


# ---------------------------------------------------------------------------
# Step 1.2 — _resolve_request_from_stdin() empty-piped-stdin fallback
# ---------------------------------------------------------------------------


def test_resolve_request_from_stdin_falls_back_to_default_on_empty_piped_input(
    monkeypatch,
):
    """A piped-but-empty stdin (e.g. `< /dev/null` in a hook/CI invocation)
    must resolve to "default request", the same as an interactive tty with
    no input — testing stdin CONTENT, not just whether it's a tty, since an
    empty request now drives live persona dispatch (Research phase), not
    just classify()."""
    fake_stdin = io.StringIO("")
    monkeypatch.setattr(fake_stdin, "isatty", lambda: False)
    monkeypatch.setattr(orch.sys, "stdin", fake_stdin)

    assert orch._resolve_request_from_stdin() == "default request"


def test_resolve_request_from_stdin_falls_back_to_default_on_whitespace_only_input(
    monkeypatch,
):
    """Whitespace-only piped stdin (e.g. a stray newline) must also fall
    back to "default request", not an empty/whitespace request."""
    fake_stdin = io.StringIO("\n  \n")
    monkeypatch.setattr(fake_stdin, "isatty", lambda: False)
    monkeypatch.setattr(orch.sys, "stdin", fake_stdin)

    assert orch._resolve_request_from_stdin() == "default request"


def test_resolve_request_from_stdin_returns_piped_content_when_present(monkeypatch):
    fake_stdin = io.StringIO("implement feature X")
    monkeypatch.setattr(fake_stdin, "isatty", lambda: False)
    monkeypatch.setattr(orch.sys, "stdin", fake_stdin)

    assert orch._resolve_request_from_stdin() == "implement feature X"


def test_resolve_request_from_stdin_returns_default_on_interactive_tty(monkeypatch):
    """Non-empty content must still be ignored when isatty() is True — an
    empty-stdin fixture would pass even if the isatty() guard were removed
    or inverted, since empty content already defaults regardless of the tty
    branch. Real piped text proves the guard, not just agrees with it."""
    fake_stdin = io.StringIO("real piped text, should be ignored")
    monkeypatch.setattr(fake_stdin, "isatty", lambda: True)
    monkeypatch.setattr(orch.sys, "stdin", fake_stdin)

    assert orch._resolve_request_from_stdin() == "default request"


# ---------------------------------------------------------------------------
# Step 6.1 — Task classification and fast-path branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_trivial_stub_takes_fast_path():
    """With classify_fn returning trivial, run_pipeline() must NOT call phase functions."""
    called = []

    async def stub_research(request, task, skip_llm):
        called.append("research")
        return {"result": "research_done"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="fix typo",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "trivial"},
            phase_research_fn=stub_research,
        )

    assert exit_code == 0
    assert "research" not in called, (
        "research phase should be skipped for trivial tasks"
    )


@pytest.mark.asyncio
async def test_classify_standard_calls_research_phase():
    """With classify_fn returning standard, run_pipeline() must call research phase."""
    called = []

    async def stub_research(request, task, skip_llm):
        called.append("research")
        return {"result": "research_done"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="implement feature X",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_research_fn=stub_research,
        )

    assert exit_code == 0
    assert "research" in called, "research phase should run for standard tasks"


@pytest.mark.asyncio
async def test_classify_fallback_on_llm_unavailable():
    """When `claude` is not on PATH, subprocess.run raises FileNotFoundError;
    classify() must catch it and fall back to the exact safe default."""
    with patch.object(orch.subprocess, "run", side_effect=FileNotFoundError):
        result = await orch.classify("do something", skip_llm=False)
    assert result == {"size": "standard"}


@pytest.mark.skipif(
    os.environ.get("ORCHESTRATOR_REAL_SUBPROCESS_TESTS") != "1",
    reason=(
        "shells out to the real `claude` CLI with a 30s timeout and its "
        "outcome/latency/cost vary by host; opt in with "
        "ORCHESTRATOR_REAL_SUBPROCESS_TESTS=1 on a host with `claude` on "
        "PATH. Mirrors the opt-in pattern in "
        "test_csharp_stryker_net_wrapper.py's TestSignalHandlingPOSIX."
    ),
)
@pytest.mark.asyncio
async def test_classify_real_subprocess_returns_valid_size():
    """Real-subprocess probe: classify() against the actual `claude` CLI
    must still return a dict with a valid 'size', whatever the classification."""
    result = await orch.classify("do something", skip_llm=False)
    assert "size" in result
    assert result["size"] in ("trivial", "standard", "complex")


# ---------------------------------------------------------------------------
# Step 6.2 — Phase state persistence and --resume
# ---------------------------------------------------------------------------


def test_write_and_read_progress():
    """write_progress writes JSON; read_progress reads it back correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        payload = {"result": "done", "files": ["a.py", "b.py"]}
        orch.write_progress("research", payload, memory_dir)
        got = orch.read_progress("research", memory_dir)
    assert got == payload


def test_read_progress_returns_none_when_missing():
    """read_progress returns None when no state file exists."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        result = orch.read_progress("plan", memory_dir)
    assert result is None


@pytest.mark.asyncio
async def test_resume_skips_research_when_state_present():
    """With --resume and an existing research state file, research fn is NOT called."""
    called = []

    async def stub_research(request, task, skip_llm):
        called.append("research")
        return {"result": "research_done"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        # Pre-seed research state
        orch.write_progress("research", {"result": "prior", "files": []}, memory_dir)

        exit_code = await orch.run_pipeline(
            request="implement feature X",
            memory_dir=memory_dir,
            skip_llm=True,
            resume=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_research_fn=stub_research,
        )

    assert exit_code == 0
    assert "research" not in called, (
        "research should be skipped when prior state exists"
    )


@pytest.mark.asyncio
async def test_phase_state_written_after_research():
    """After a successful pipeline run, a research state file must exist."""

    async def stub_research(request, task, skip_llm):
        return {"result": "done", "files": []}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        await orch.run_pipeline(
            request="implement feature X",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_research_fn=stub_research,
        )
        state = orch.read_progress("research", memory_dir)

    assert state is not None
    assert state.get("result") == "done"


# ---------------------------------------------------------------------------
# Step 6.3 — Concurrent persona dispatch and wave barrier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_personas_concurrently():
    """dispatch_personas must return one result per persona (gather semantics)."""
    personas = ["acceptance-test-critic", "design-architecture-critic"]
    results = await orch.dispatch_personas(personas, plan={"spec": "x"}, skip_llm=True)
    assert len(results) == len(personas)
    returned_personas = {r["persona"] for r in results}
    assert returned_personas == set(personas)


@pytest.mark.asyncio
async def test_dispatch_personas_maps_unexpected_exception_to_failed_stub_without_dropping_siblings():
    """An exception escaping one persona's dispatch_persona call (anything
    outside its own try/except's catch tuple) must not cancel or discard
    the other personas' results — dispatch_personas maps it to a failure
    stub, via asyncio.gather(..., return_exceptions=True), using a distinct
    "dispatch_exception" error code rather than dispatch_persona's own
    "llm_unavailable": this branch means something threw out of the
    coroutine itself, not that the CLI/subprocess failed."""

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        if persona == "architect":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad byte")
        return {"persona": persona, "status": "success"}

    with patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona):
        results = await orch.dispatch_personas(
            ["codebase-recon", "architect", "data-flow-tracer"], plan={}, skip_llm=False
        )

    assert len(results) == 3
    by_persona = {r["persona"]: r for r in results}
    assert by_persona["codebase-recon"]["status"] == "success"
    assert by_persona["data-flow-tracer"]["status"] == "success"
    assert by_persona["architect"] == {
        "persona": "architect",
        "status": "failed",
        "error": "dispatch_exception",
    }


@pytest.mark.asyncio
async def test_dispatch_personas_maps_cancelled_error_to_failed_stub():
    """asyncio.CancelledError is a BaseException, not an Exception (since
    Python 3.8) — a child task cancelled under
    asyncio.gather(..., return_exceptions=True) must still normalize to the
    same failure stub as any other unexpected throwable, not fall through
    unmapped and later break write_progress's json.dumps of the aggregated
    research state."""

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        if persona == "architect":
            raise asyncio.CancelledError()
        return {"persona": persona, "status": "success"}

    with patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona):
        results = await orch.dispatch_personas(
            ["codebase-recon", "architect", "data-flow-tracer"], plan={}, skip_llm=False
        )

    assert len(results) == 3
    by_persona = {r["persona"]: r for r in results}
    assert by_persona["codebase-recon"]["status"] == "success"
    assert by_persona["data-flow-tracer"]["status"] == "success"
    assert by_persona["architect"] == {
        "persona": "architect",
        "status": "failed",
        "error": "dispatch_exception",
    }
    json.dumps(results)  # must not raise — the exact failure mode this guards against


@pytest.mark.asyncio
async def test_dispatch_persona_prints_startup_line(capsys):
    """Each persona dispatch must print an INFO startup line to stderr."""
    await orch.dispatch_persona("acceptance-test-critic", plan={}, skip_llm=True)
    captured = capsys.readouterr()
    assert "dispatching persona" in captured.err
    assert "plan-review" not in captured.err
    assert "acceptance-test-critic" in captured.err


@pytest.mark.asyncio
async def test_wave_error_raised_on_failed_slice():
    """reconcile() must raise WaveError when any result has status='failed'."""
    results = [
        {"slice": "slice-1", "status": "success"},
        {"slice": "slice-2", "status": "failed"},
    ]
    wave_slices = ["slice-1", "slice-2"]

    with pytest.raises(orch.WaveError) as exc_info:
        await orch.reconcile(results, wave_slices)

    err = exc_info.value
    assert err.failing_slice == "slice-2"
    assert "slice-1" in err.succeeded


@pytest.mark.asyncio
async def test_wave_error_not_raised_on_all_success():
    """reconcile() must NOT raise when all slices succeed."""
    results = [
        {"slice": "slice-1", "status": "success"},
        {"slice": "slice-2", "status": "success"},
    ]
    # Should not raise
    await orch.reconcile(results, ["slice-1", "slice-2"])


# ---------------------------------------------------------------------------
# Step 1.2 — dispatch_persona via claude -p --agent --output-format json
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    """Minimal stand-in for subprocess.CompletedProcess — only .stdout is read."""

    def __init__(self, stdout: str):
        self.stdout = stdout
        self.returncode = 0


@pytest.mark.asyncio
async def test_dispatch_persona_invokes_real_cli_with_agent_and_json_flags():
    """dispatch_persona must call subprocess.run with --agent <persona> and
    --output-format json, sending the plan payload as the prompt (not a
    hand-rolled role-play string). A successful, non-error envelope for a
    non-JSON-contract persona must map to status "success" with the raw
    result text stored under "output"."""
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        envelope = json.dumps({"is_error": False, "result": "PONG"})
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "software-engineer", plan={"task": "do X"}, skip_llm=False
        )

    argv = captured["argv"]
    assert "--agent" in argv
    assert argv[argv.index("--agent") + 1] == "software-engineer"
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    prompt = argv[-1]
    assert "do X" in prompt
    assert "You are the software-engineer" not in prompt

    assert result == {
        "persona": "software-engineer",
        "status": "success",
        "output": "PONG",
    }


@pytest.mark.asyncio
async def test_dispatch_persona_is_error_true_maps_to_failed_status():
    """A JSON envelope with is_error=true must map to status "failed", with
    the prose result still stored under "output" for a non-JSON-contract
    persona."""

    def fake_run(argv, **kwargs):
        envelope = json.dumps({"is_error": True, "result": "boom"})
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "software-engineer", plan={}, skip_llm=False
        )

    assert result == {
        "persona": "software-engineer",
        "status": "failed",
        "output": "boom",
    }


@pytest.mark.asyncio
async def test_dispatch_persona_skip_llm_returns_success_stub_without_subprocess():
    """skip_llm=True must short-circuit without invoking subprocess.run and
    return a stub result with status "success"."""
    with patch.object(orch.subprocess, "run") as mock_run:
        result = await orch.dispatch_persona(
            "plan-review-acceptance", plan={}, skip_llm=True
        )

    mock_run.assert_not_called()
    assert result["persona"] == "plan-review-acceptance"
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_dispatch_persona_json_contract_persona_result_is_parsed_and_merged():
    """A plan-review-* (JSON_CONTRACT_PERSONAS) persona's result text, when
    valid JSON, must be parsed and its keys merged into the returned dict —
    not stored under "output"."""

    def fake_run(argv, **kwargs):
        inner = json.dumps({"verdict": "approve", "issues": []})
        envelope = json.dumps({"is_error": False, "result": inner})
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "plan-review-acceptance", plan={}, skip_llm=False
        )

    assert result["persona"] == "plan-review-acceptance"
    assert result["status"] == "success"
    assert result["verdict"] == "approve"
    assert result["issues"] == []
    assert "output" not in result


@pytest.mark.asyncio
async def test_dispatch_persona_code_review_panel_result_is_parsed_and_merged():
    """A CODE_REVIEW_PANEL persona (doc-review) result text, when valid JSON
    matching the review-agent-output-contract schema, must be parsed and its
    status/issues/summary keys merged into the returned dict."""

    def fake_run(argv, **kwargs):
        inner = json.dumps({"status": "pass", "issues": [], "summary": "ok"})
        envelope = json.dumps({"is_error": False, "result": inner})
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona("doc-review", plan={}, skip_llm=False)

    assert result["persona"] == "doc-review"
    assert result["status"] == "success"
    assert result["review_status"] == "pass"
    assert result["issues"] == []
    assert result["summary"] == "ok"
    assert "output" not in result


@pytest.mark.asyncio
async def test_dispatch_persona_json_contract_persona_array_result_degrades():
    """A JSON_CONTRACT_PERSONAS dispatch whose inner result parses as valid
    JSON but is not a JSON object (e.g. a bare array) must degrade to the
    output+parse_error path, not raise ValueError out of dispatch_persona."""

    def fake_run(argv, **kwargs):
        # A JSON array whose elements would raise ValueError (not TypeError)
        # from dict.update() — element "bcd" has length 3, not 2, so
        # dict.update() cannot unpack it as a (key, value) pair. Confirms
        # the fix isn't merely catching TypeError from other array shapes.
        envelope = json.dumps({"is_error": False, "result": '["a", "bcd"]'})
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "plan-review-acceptance", plan={}, skip_llm=False
        )

    assert result == {
        "persona": "plan-review-acceptance",
        "status": "success",
        "output": '["a", "bcd"]',
        "parse_error": True,
    }


@pytest.mark.asyncio
async def test_dispatch_persona_json_contract_persona_invalid_inner_json_degrades():
    """A JSON_CONTRACT_PERSONAS dispatch whose inner result text is not valid
    JSON must degrade to storing the raw text under "output" plus a
    parse_error marker, with status still driven by the outer envelope's
    is_error field, unaffected by the inner parse failure."""

    def fake_run(argv, **kwargs):
        envelope = json.dumps(
            {"is_error": False, "result": "not valid json at all"}
        )
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "plan-review-acceptance", plan={}, skip_llm=False
        )

    assert result == {
        "persona": "plan-review-acceptance",
        "status": "success",
        "output": "not valid json at all",
        "parse_error": True,
    }


@pytest.mark.asyncio
async def test_dispatch_persona_missing_is_error_key_defaults_to_failed():
    """An envelope that parses but omits the is_error key entirely must
    default to status "failed" — the absence of is_error is not evidence of
    success."""

    def fake_run(argv, **kwargs):
        envelope = json.dumps({"result": "no is_error key present"})
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "software-engineer", plan={}, skip_llm=False
        )

    assert result["status"] == "failed"


@pytest.mark.parametrize(
    "persona", ["plan-review-acceptance", "software-engineer"]
)
@pytest.mark.parametrize(
    "side_effect",
    [
        FileNotFoundError(),
        subprocess.TimeoutExpired(cmd="claude", timeout=60),
    ],
)
@pytest.mark.asyncio
async def test_dispatch_persona_subprocess_exception_maps_to_failed_stub(
    persona, side_effect
):
    """A subprocess exception (FileNotFoundError, TimeoutExpired) must map to
    the generalized failure stub — status "failed", error "llm_unavailable",
    and no "verdict" key at all — for both a critic and a non-critic
    persona."""
    with patch.object(orch.subprocess, "run", side_effect=side_effect):
        result = await orch.dispatch_persona(persona, plan={}, skip_llm=False)

    assert result == {
        "persona": persona,
        "status": "failed",
        "error": "llm_unavailable",
    }
    assert "verdict" not in result


@pytest.mark.asyncio
async def test_dispatch_persona_non_serializable_plan_maps_to_failed_stub():
    """A non-JSON-serializable plan value (e.g. a set, which json.dumps
    rejects with TypeError) must degrade to a failure stub — via its own
    narrow try/except, scoped to serialization only — rather than raise out
    of the coroutine and break dispatch_personas' asyncio.gather fan-out for
    sibling personas. Distinct error code from a subprocess/CLI failure
    ("unserializable_plan" vs. "llm_unavailable"): this is a caller-side bug
    in the dispatched plan payload, not the LLM being unavailable, and the
    two must stay distinguishable in the persisted research state."""
    with patch.object(orch.subprocess, "run") as mock_run:
        result = await orch.dispatch_persona(
            "architect", plan={"not_serializable": {1, 2, 3}}, skip_llm=False
        )

    mock_run.assert_not_called()
    assert result == {
        "persona": "architect",
        "status": "failed",
        "error": "unserializable_plan",
    }


@pytest.mark.parametrize(
    "persona", ["plan-review-acceptance", "software-engineer"]
)
@pytest.mark.asyncio
async def test_dispatch_persona_malformed_envelope_maps_to_failed_stub(persona):
    """A malformed (non-JSON) top-level --output-format json envelope must
    map to the failure stub, not raise, for both a critic and a non-critic
    persona. Distinct error code from a subprocess/CLI failure
    ("malformed_envelope" vs. "llm_unavailable"): here the CLI ran and
    returned bytes, they just weren't parseable JSON — a different cause
    than the CLI being unreachable, and the persisted research state must
    keep the two distinguishable."""

    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess("not json at all {")

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(persona, plan={}, skip_llm=False)

    assert result == {
        "persona": persona,
        "status": "failed",
        "error": "malformed_envelope",
    }
    assert "verdict" not in result


@pytest.mark.parametrize(
    "persona", ["plan-review-acceptance", "software-engineer"]
)
@pytest.mark.asyncio
async def test_dispatch_persona_non_object_envelope_maps_to_failed_stub(persona):
    """A top-level envelope that is syntactically valid JSON but not a JSON
    object (e.g. a bare array) must degrade to the "malformed_envelope"
    failure stub, not raise AttributeError from envelope.get() on a
    non-dict, for both a critic and a non-critic persona."""

    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess("[1, 2, 3]")

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(persona, plan={}, skip_llm=False)

    assert result == {
        "persona": persona,
        "status": "failed",
        "error": "malformed_envelope",
    }
    assert "verdict" not in result


@pytest.mark.asyncio
async def test_dispatch_persona_json_contract_outer_error_survives_valid_inner_pass():
    """When the outer envelope reports is_error=true but the inner result is
    still valid JSON with its own "status": "pass", the dispatch-level status
    must stay "failed" (derived from is_error) while the parsed verdict is
    exposed separately as review_status — the merge must never let a
    successful-looking inner payload overwrite a real dispatch failure."""

    def fake_run(argv, **kwargs):
        envelope = json.dumps(
            {
                "is_error": True,
                "result": json.dumps({"status": "pass", "summary": "ok"}),
            }
        )
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "plan-review-acceptance", plan={}, skip_llm=False
        )

    assert result["status"] == "failed"
    assert result["review_status"] == "pass"


@pytest.mark.asyncio
async def test_dispatch_persona_json_contract_inner_persona_key_does_not_clobber():
    """A conflicting "persona" key inside the parsed inner result must not
    overwrite the dispatch-owned persona name — proving the `elif key ==
    "persona": continue` guard is actually exercised."""

    def fake_run(argv, **kwargs):
        envelope = json.dumps(
            {
                "is_error": False,
                "result": json.dumps(
                    {"persona": "someone-else", "status": "pass"}
                ),
            }
        )
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "plan-review-acceptance", plan={}, skip_llm=False
        )

    assert result["persona"] == "plan-review-acceptance"


@pytest.mark.asyncio
async def test_dispatch_persona_json_contract_inner_result_null_degrades():
    """An outer envelope whose "result" field is an explicit JSON null (not
    omitted — envelope.get("result", "") returns None for an explicit null,
    since the default only applies when the key is absent) must degrade to
    the output+parse_error path via the existing TypeError arm, not raise."""

    def fake_run(argv, **kwargs):
        envelope = json.dumps({"is_error": False, "result": None})
        return _FakeCompletedProcess(envelope)

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(
            "plan-review-acceptance", plan={}, skip_llm=False
        )

    assert result["status"] == "success"
    assert result["output"] is None
    assert result["parse_error"] is True


@pytest.mark.asyncio
async def test_gather_called_with_two_tasks_for_two_personas():
    """asyncio.gather must be called with exactly two coroutines for two personas."""
    personas = ["critic-a", "critic-b"]
    # We spy on the actual gather by counting how many tasks are awaited
    dispatched = []
    original_dispatch_persona = orch.dispatch_persona

    async def counting_dispatch(persona, plan, skip_llm=False):
        dispatched.append(persona)
        return await original_dispatch_persona(persona, plan, skip_llm=True)

    with patch.object(orch, "dispatch_persona", side_effect=counting_dispatch):
        await orch.dispatch_personas(personas, plan={}, skip_llm=True)

    assert len(dispatched) == 2
    assert set(dispatched) == set(personas)


# ---------------------------------------------------------------------------
# Step 1.2 — _default_phase_research() real persona dispatch
# ---------------------------------------------------------------------------

# Independent literal, deliberately NOT set(orch.RESEARCH_PERSONAS): importing
# the production constant here would make every JSON-artifact assertion below
# self-comparing (state["personas"] is literally list(RESEARCH_PERSONAS) echoed
# through write_progress) — the whole point of these tests is verifying
# run_pipeline actually wrote the roster it dispatched, not that the constant
# equals itself.
RESEARCH_ALWAYS_ON = {"codebase-recon", "architect", "data-flow-tracer"}


def _capturing_dispatch_personas_stub(captured):
    """Return a dispatch_personas fake that records its call args into
    `captured` and returns a canned all-success result per persona. Shared
    by the persona-selection tests below to avoid re-typing the same
    capture-and-return double five times (test-smell finding)."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        captured["personas"] = personas
        captured["plan"] = plan
        captured["skip_llm"] = skip_llm
        return [{"persona": p, "status": "success"} for p in personas]

    return fake_dispatch_personas


@pytest.mark.asyncio
async def test_default_phase_research_standard_dispatches_three_always_on_personas(capsys):
    """A standard-classified request with no security signal dispatches
    exactly the three always-on personas."""
    captured = {}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_stub(captured)
    ):
        result = await orch._default_phase_research(
            "add a login form", {"size": "standard"}, skip_llm=True
        )

    assert set(captured["personas"]) == RESEARCH_ALWAYS_ON
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(captured["personas"]) == len(RESEARCH_ALWAYS_ON)
    # Independent expected literal, not a self-comparison against `captured`
    # (result["personas"] is literally the same list _default_phase_research
    # built and dispatch_personas echoed back — comparing it to `captured`
    # would only fail if the "personas" key itself went missing). Set
    # equality, not list equality: the approved plan's Step 1.2 explicitly
    # states dispatch order is not a contract.
    assert set(result["personas"]) == RESEARCH_ALWAYS_ON
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(result["personas"]) == len(RESEARCH_ALWAYS_ON)
    # Negative case for the failed-persona WARNING: an all-success dispatch
    # must print nothing about failures.
    assert "WARNING: Research persona dispatch failed" not in capsys.readouterr().err
    assert result["skip_llm"] is True


@pytest.mark.asyncio
async def test_default_phase_research_complex_dispatches_same_always_on_personas():
    """A complex-classified request dispatches the identical always-on trio
    — the only branch point in run_pipeline is the trivial fast-path, so a
    future complex-specific special case must not regress this silently."""
    captured = {}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_stub(captured)
    ):
        await orch._default_phase_research(
            "redesign the payment pipeline", {"size": "complex"}, skip_llm=True
        )

    assert set(captured["personas"]) == RESEARCH_ALWAYS_ON
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(captured["personas"]) == len(RESEARCH_ALWAYS_ON)


@pytest.mark.asyncio
async def test_default_phase_research_adds_security_engineer_when_request_touches_security():
    captured = {}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_stub(captured)
    ):
        await orch._default_phase_research(
            "rotate the API secret token", {"size": "standard"}, skip_llm=True
        )

    assert set(captured["personas"]) == RESEARCH_ALWAYS_ON | {orch.SECURITY_ENGINEER_PERSONA}
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(captured["personas"]) == len(RESEARCH_ALWAYS_ON) + 1


@pytest.mark.asyncio
async def test_default_phase_research_omits_security_engineer_when_no_signal():
    captured = {}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_stub(captured)
    ):
        await orch._default_phase_research(
            "fix a typo in the README", {"size": "standard"}, skip_llm=True
        )

    # Full expected set, not just the negative "security-engineer not in ...":
    # a regression that also dropped e.g. "architect" from the always-on
    # trio would still pass a bare `not in` check.
    assert set(captured["personas"]) == RESEARCH_ALWAYS_ON
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(captured["personas"]) == len(RESEARCH_ALWAYS_ON)


def _seed_recon_artifact(tmp_path):
    """Create a fake .claude/memory/recon-<slug>.json under tmp_path and
    return its Path. Shared by the recon-artifact tests below that need an
    existing-on-disk artifact, avoiding re-typing the same four-line setup
    (test-smell finding, matching this file's existing
    _capturing_dispatch_personas_stub extraction rationale)."""
    recon_dir = tmp_path / ".claude" / "memory"
    recon_dir.mkdir(parents=True)
    slug = orch.derive_slug(tmp_path)
    artifact = recon_dir / f"recon-{slug}.json"
    artifact.write_text("{}")
    return artifact


@pytest.mark.asyncio
async def test_default_phase_research_links_recon_artifact_when_present(tmp_path, monkeypatch):
    """When codebase-recon succeeds and its artifact file exists on disk,
    the Research state links to it (follow-up #1716)."""
    monkeypatch.chdir(tmp_path)
    artifact = _seed_recon_artifact(tmp_path)

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_stub({})
    ):
        result = await orch._default_phase_research(
            "add a login form", {"size": "standard"}, skip_llm=False
        )

    assert result["recon_artifact"] == str(artifact)


@pytest.mark.asyncio
async def test_default_phase_research_recon_artifact_none_when_file_missing(tmp_path, monkeypatch):
    """codebase-recon reporting success doesn't guarantee its artifact
    exists on disk (e.g. --skip-llm never runs the real agent) — the link
    is None rather than a dangling path in that case."""
    monkeypatch.chdir(tmp_path)

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_stub({})
    ):
        result = await orch._default_phase_research(
            "add a login form", {"size": "standard"}, skip_llm=True
        )

    assert result["recon_artifact"] is None


@pytest.mark.asyncio
async def test_default_phase_research_recon_artifact_none_when_recon_failed(tmp_path, monkeypatch):
    """A failed codebase-recon dispatch never links its artifact, even if a
    stale file from a prior run happens to exist at that path."""
    monkeypatch.chdir(tmp_path)
    _seed_recon_artifact(tmp_path)

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        return [
            {"persona": p, "status": "failed" if p == "codebase-recon" else "success"}
            for p in personas
        ]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        result = await orch._default_phase_research(
            "add a login form", {"size": "standard"}, skip_llm=False
        )

    assert result["recon_artifact"] is None


@pytest.mark.asyncio
async def test_default_phase_research_calls_dispatch_personas_with_task_and_request_in_plan():
    """The mock must be called with plan={"task": task, "request": request}
    — checked directly on the call arguments, not just inferred from the
    return value — so a silent drop of "request" from the payload fails
    this test."""
    captured = {}

    task = {"size": "standard"}
    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_stub(captured)
    ):
        await orch._default_phase_research("add a login form", task, skip_llm=True)

    assert captured["plan"] == {"task": task, "request": "add a login form"}
    assert captured["skip_llm"] is True


@pytest.mark.asyncio
async def test_run_pipeline_with_real_research_fn_writes_expected_json_shape(tmp_path, monkeypatch):
    """orchestrator-research.json's contents after a full run_pipeline run
    with the real (non-stub) research function and skip_llm=True match the
    {personas, results, skip_llm, recon_artifact} shape, using set-equality
    on personas.

    Chdir's to an isolated tmp_path (rather than leaving CWD as whatever the
    test runner's real invocation directory happens to be): recon_artifact
    is resolved off Path.cwd(), so without this isolation the assertion
    below would depend on whether a real .claude/memory/recon-<slug>.json
    happens to exist wherever the suite is run from — a prior real
    orchestrator run against this repo would silently flip this red with no
    related code change (test-smell finding)."""
    monkeypatch.chdir(tmp_path)
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    assert set(state.keys()) == {"personas", "results", "skip_llm", "recon_artifact"}
    assert set(state["personas"]) == RESEARCH_ALWAYS_ON
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(state["personas"]) == len(RESEARCH_ALWAYS_ON)
    assert state["skip_llm"] is True
    assert {r["persona"] for r in state["results"]} == set(state["personas"])
    assert all(r["status"] == "success" for r in state["results"])
    # skip_llm=True never runs the real codebase-recon agent, so no artifact
    # file exists on disk regardless of dispatch success.
    assert state["recon_artifact"] is None
    # skip_llm's stub contract (dispatch_persona) returns bare
    # {persona, status} — no "output"/"review_status" field. Asserting their
    # absence, not just status == "success", is what distinguishes a genuine
    # skip_llm stub result from a live-CLI response that happened to succeed.
    assert all("output" not in r and "review_status" not in r for r in state["results"])


@pytest.mark.asyncio
async def test_run_pipeline_with_real_research_fn_includes_security_engineer_in_written_json():
    """The security-engineer-added scenario verified through the real
    run_pipeline -> write_progress path, not just the mocked-dispatch unit
    test above — closing the gap between the approved plan's Gherkin (which
    specifies orchestrator-research.json's "personas" key as the observable
    for this exact scenario) and what the mocked-dispatch tests alone would
    catch."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="rotate the API secret token",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    assert set(state["personas"]) == RESEARCH_ALWAYS_ON | {orch.SECURITY_ENGINEER_PERSONA}
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(state["personas"]) == len(RESEARCH_ALWAYS_ON) + 1


@pytest.mark.asyncio
async def test_run_pipeline_with_real_research_fn_omits_security_engineer_in_written_json():
    """The security-engineer-omitted scenario verified through the real
    run_pipeline -> write_progress path — same rationale as the
    security-engineer-included counterpart above."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="fix a typo in the README",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    assert set(state["personas"]) == RESEARCH_ALWAYS_ON
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(state["personas"]) == len(RESEARCH_ALWAYS_ON)
    assert orch.SECURITY_ENGINEER_PERSONA not in state["personas"]


@pytest.mark.asyncio
async def test_run_pipeline_with_real_research_fn_complex_classification_writes_json():
    """The complex-classification scenario verified through the real
    run_pipeline -> write_progress path, not just the mocked-dispatch unit
    test — run_pipeline's only branch point is the trivial fast-path
    (task.get("size") == "trivial"), so this is what actually exercises the
    "a future complex-specific special case must not regress this silently"
    rationale the scenario exists for."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="redesign the payment pipeline",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "complex"},
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    assert set(state["personas"]) == RESEARCH_ALWAYS_ON
    # Cardinality check (follow-up #1716): set-equality alone wouldn't
    # catch a future accidental double-append to the persona list.
    assert len(state["personas"]) == len(RESEARCH_ALWAYS_ON)


@pytest.mark.asyncio
async def test_run_pipeline_with_real_research_fn_case_insensitive_security_signal_writes_json():
    """The case-insensitive security-heuristic scenario verified through the
    real run_pipeline -> write_progress path, using the Gherkin's literal
    request text — the one prior run_pipeline-level security-add test uses
    an all-lowercase request, so this is the only coverage of the mixed-case
    path through the full pipeline, not just _touches_security() in
    isolation."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="AUTHENTICATE the user via OAuth",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    assert orch.SECURITY_ENGINEER_PERSONA in state["personas"]


@pytest.mark.asyncio
async def test_trivial_task_never_calls_dispatch_personas_with_real_research_fn():
    """trivial-classified tasks still never call dispatch_personas or write
    orchestrator-research.json, re-verified against the real (non-stub)
    research function."""
    with (
        patch.object(orch, "dispatch_personas") as mock_dispatch,
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="fix a typo",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "trivial"},
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    mock_dispatch.assert_not_called()
    assert state is None


@pytest.mark.asyncio
async def test_resume_skips_dispatch_and_leaves_file_unchanged_with_real_research_fn():
    """--resume with a pre-seeded orchestrator-research.json still skips
    Research dispatch entirely and leaves the file unchanged, re-verified
    against the real (non-stub) research function.

    Scoped to Research alone via no-op phase_plan_fn/phase_implement_fn
    stubs: this test pre-seeds only orchestrator-research.json (no
    orchestrator-plan.json or orchestrator-implement.json), which is also
    the realistic "Research done, Plan pending" partial-resume shape —
    Plan-phase dispatch behavior for that shape has its own dedicated
    coverage (test_resume_with_research_done_dispatches_plan_using_resumed_research_state
    below); this test's purpose stays narrowly "Research's own resume-skip
    still works", so it must not depend on how Plan's or Implement's real
    dispatch handles a bare, non-list-returning mock_dispatch."""

    async def noop_phase_plan_fn(request, task, research_state, skip_llm):
        return {"stub": "plan"}

    async def noop_phase_implement_fn(request, task, plan_state, skip_llm):
        return {"stub": "implement"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        prior_state = {
            "personas": ["codebase-recon"],
            "results": [],
            "skip_llm": True,
        }
        orch.write_progress("research", prior_state, memory_dir)
        pre_run_contents = orch.phase_state_path("research", memory_dir).read_text()

        with patch.object(orch, "dispatch_personas") as mock_dispatch:
            exit_code = await orch.run_pipeline(
                request="add a login form",
                memory_dir=memory_dir,
                skip_llm=True,
                resume=True,
                classify_fn=lambda req: {"size": "standard"},
                phase_plan_fn=noop_phase_plan_fn,
                phase_implement_fn=noop_phase_implement_fn,
            )

        post_run_contents = orch.phase_state_path("research", memory_dir).read_text()

    assert exit_code == 0
    mock_dispatch.assert_not_called()
    assert post_run_contents == pre_run_contents


@pytest.mark.asyncio
async def test_default_phase_research_records_one_failed_persona_verbatim_without_raising(
    capsys,
):
    """A faked dispatch_personas result list — one status: "failed" entry
    and two status: "success" entries, matching the three-persona
    ("add a login form") case — is recorded verbatim in the written JSON,
    does not raise WaveError, and run_pipeline still returns exit code 0.
    Also the one case (unlike the all-failed/all-success tests) that can
    prove the stderr WARNING names only the failed persona, not the whole
    roster — a mutant that joined `personas` instead of `failed_personas`
    would still pass those two degenerate tests but fail this one.

    Scoped to Research alone via no-op phase_plan_fn/phase_implement_fn
    stubs: dispatch_personas is patched globally (it must be, to fake
    Research's own dispatch), so without stubs the same fake would also
    serve Plan's and Implement's dispatch calls — merging extra WARNINGs
    into this test's stderr and (for Implement) breaking on the
    slice-tagging/reconcile() machinery since fake_results carries no
    "slice" key — muddying what this test is actually asserting."""
    fake_results = [
        {"persona": "codebase-recon", "status": "success"},
        {"persona": "architect", "status": "failed", "error": "llm_unavailable"},
        {"persona": "data-flow-tracer", "status": "success"},
    ]

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        return fake_results

    async def noop_phase_plan_fn(request, task, research_state, skip_llm):
        return {"stub": "plan"}

    async def noop_phase_implement_fn(request, task, plan_state, skip_llm):
        return {"stub": "implement"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_plan_fn=noop_phase_plan_fn,
            phase_implement_fn=noop_phase_implement_fn,
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    assert state["results"] == fake_results
    stderr = capsys.readouterr().err
    assert "WARNING: Research persona dispatch failed" in stderr
    assert "architect" in stderr
    assert "codebase-recon" not in stderr
    assert "data-flow-tracer" not in stderr


@pytest.mark.asyncio
async def test_default_phase_research_records_all_personas_failed_verbatim_without_raising(
    capsys,
):
    """The boundary case of all three personas failing is also recorded
    verbatim — record, don't raise — not just the one-of-three partial
    failure case above. Also asserts the stderr WARNING _default_phase_research
    prints when any persona failed, naming each failed persona — otherwise a
    run where every persona failed would look identical, on the console, to
    one that fully succeeded.

    Scoped to Research alone via no-op phase_plan_fn/phase_implement_fn
    stubs — see the identical rationale on
    test_default_phase_research_records_one_failed_persona_verbatim_without_raising
    above: without them, this same fake would also serve Plan's and
    Implement's dispatch calls."""
    fake_results = [
        {"persona": "codebase-recon", "status": "failed", "error": "llm_unavailable"},
        {"persona": "architect", "status": "failed", "error": "llm_unavailable"},
        {
            "persona": "data-flow-tracer",
            "status": "failed",
            "error": "llm_unavailable",
        },
    ]

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        return fake_results

    async def noop_phase_plan_fn(request, task, research_state, skip_llm):
        return {"stub": "plan"}

    async def noop_phase_implement_fn(request, task, plan_state, skip_llm):
        return {"stub": "implement"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_plan_fn=noop_phase_plan_fn,
            phase_implement_fn=noop_phase_implement_fn,
        )
        state = orch.read_progress("research", memory_dir)

    assert exit_code == 0
    assert state["results"] == fake_results
    stderr = capsys.readouterr().err
    assert "WARNING: Research persona dispatch failed" in stderr
    assert "codebase-recon" in stderr
    assert "architect" in stderr
    assert "data-flow-tracer" in stderr


# ---------------------------------------------------------------------------
# Step 1.2 — _default_phase_plan() two-stage dispatch (core trio, then critics)
# ---------------------------------------------------------------------------


def _capturing_dispatch_personas_recorder(calls):
    """Return a dispatch_personas fake that appends each call's args (as a
    dict) to `calls`, in call order, and returns a canned all-success result
    per persona. Shared helper for the _default_phase_plan tests below,
    mirroring _capturing_dispatch_personas_stub's single-call variant above
    but supporting the two-call (core trio, then critics) sequence."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        calls.append({"personas": personas, "plan": plan, "skip_llm": skip_llm})
        return [{"persona": p, "status": "success"} for p in personas]

    return fake_dispatch_personas


@pytest.mark.asyncio
async def test_default_phase_plan_dispatches_core_trio_first_then_critics():
    """_default_phase_plan must call dispatch_personas exactly twice: first
    with PLAN_CORE_PERSONAS, then with DEFAULT_PERSONAS (the five
    plan-review-* critics) — in that order."""
    calls = []
    task = {"size": "standard"}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_recorder(calls)
    ):
        await orch._default_phase_plan(
            "add a login form", task, research_state={"personas": []}, skip_llm=True
        )

    assert len(calls) == 2
    assert calls[0]["personas"] == list(orch.PLAN_CORE_PERSONAS)
    assert calls[1]["personas"] == orch.DEFAULT_PERSONAS


@pytest.mark.asyncio
async def test_default_phase_plan_core_trio_payload_has_task_request_and_research():
    """The first (core trio) dispatch_personas call's plan payload must be
    {"task": task, "request": request, "research": research_state}."""
    calls = []
    task = {"size": "standard"}
    research_state = {"personas": ["codebase-recon"], "results": [], "skip_llm": True}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_recorder(calls)
    ):
        await orch._default_phase_plan(
            "add a login form", task, research_state=research_state, skip_llm=True
        )

    assert calls[0]["plan"] == {
        "task": task,
        "request": "add a login form",
        "research": research_state,
    }
    assert calls[0]["skip_llm"] is True


@pytest.mark.asyncio
async def test_default_phase_plan_critics_payload_has_task_request_and_plan_draft():
    """The second (critics) dispatch_personas call's plan payload must be
    {"task": task, "request": request, "plan_draft": core_results} — where
    core_results is exactly the first call's returned results."""
    calls = []
    task = {"size": "standard"}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_recorder(calls)
    ):
        await orch._default_phase_plan(
            "add a login form", task, research_state={}, skip_llm=True
        )

    expected_core_results = [
        {"persona": p, "status": "success"} for p in orch.PLAN_CORE_PERSONAS
    ]
    assert calls[1]["plan"] == {
        "task": task,
        "request": "add a login form",
        "plan_draft": expected_core_results,
    }
    assert calls[1]["skip_llm"] is True


def test_all_personas_failed_is_false_on_empty_list():
    """The emptiness check is load-bearing per the function's own docstring:
    a bare all(...) over an empty list is vacuously True, which would wrongly
    report an empty core_results as \"all failed\" and skip critic dispatch."""
    assert orch._all_personas_failed([]) is False
    assert (
        orch._all_personas_failed([{"persona": "architect", "status": "failed"}])
        is True
    )


@pytest.mark.asyncio
async def test_default_phase_plan_returns_expected_persisted_shape():
    """_default_phase_plan's return value must have exactly the persisted
    shape: core_personas, core_results, critic_personas, critic_results,
    critics_skipped_reason, skip_llm."""
    calls = []
    task = {"size": "standard"}

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_recorder(calls)
    ):
        result = await orch._default_phase_plan(
            "add a login form", task, research_state={}, skip_llm=True
        )

    assert set(result.keys()) == {
        "core_personas",
        "core_results",
        "critic_personas",
        "critic_results",
        "critics_skipped_reason",
        "skip_llm",
    }
    assert result["core_personas"] == list(orch.PLAN_CORE_PERSONAS)
    assert result["critic_personas"] == orch.DEFAULT_PERSONAS
    assert result["critic_personas"] is not orch.DEFAULT_PERSONAS
    assert result["critics_skipped_reason"] is None
    assert result["skip_llm"] is True
    assert all(r["status"] == "success" for r in result["core_results"])
    assert all(r["status"] == "success" for r in result["critic_results"])


@pytest.mark.asyncio
async def test_default_phase_plan_partial_core_failure_still_dispatches_critics():
    """A partially-failed core trio (one of three failed) must still
    dispatch critics normally against whatever draft the surviving personas
    produced, with critics_skipped_reason left None."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if personas == list(orch.PLAN_CORE_PERSONAS):
            return [
                {"persona": "product-manager", "status": "success"},
                {"persona": "architect", "status": "failed", "error": "llm_unavailable"},
                {"persona": "qa-engineer", "status": "success"},
            ]
        return [{"persona": p, "status": "success"} for p in personas]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        result = await orch._default_phase_plan(
            "add a login form", {"size": "standard"}, research_state={}, skip_llm=True
        )

    assert result["critics_skipped_reason"] is None
    assert len(result["critic_results"]) == len(orch.DEFAULT_PERSONAS)
    assert all(r["status"] == "success" for r in result["critic_results"])
    assert any(
        r["persona"] == "architect" and r["status"] == "failed"
        for r in result["core_results"]
    )


@pytest.mark.asyncio
async def test_default_phase_plan_all_core_failed_skips_critic_dispatch(capsys):
    """A wholly-failed core trio must skip critic dispatch entirely:
    dispatch_personas is called exactly once (for the core trio only),
    critic_results is an empty list, critics_skipped_reason is
    CRITICS_SKIPPED_ALL_CORE_FAILED, and the merged stderr WARNING still
    fires naming all three failed core personas even though critic_results
    is empty (guards against a mutant that breaks the
    `core_results + critic_results` concatenation only when critic_results
    is empty), and the INFO line announcing the skip fires too."""
    call_count = 0

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        nonlocal call_count
        call_count += 1
        return [
            {"persona": p, "status": "failed", "error": "llm_unavailable"}
            for p in personas
        ]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        result = await orch._default_phase_plan(
            "add a login form", {"size": "standard"}, research_state={}, skip_llm=True
        )

    assert call_count == 1
    assert result["critic_results"] == []
    assert result["critics_skipped_reason"] == orch.CRITICS_SKIPPED_ALL_CORE_FAILED
    stderr = capsys.readouterr().err
    assert "WARNING: Plan persona dispatch failed" in stderr
    for persona in orch.PLAN_CORE_PERSONAS:
        assert persona in stderr
    assert "INFO: all Plan core personas failed — skipping critic dispatch" in stderr


@pytest.mark.asyncio
async def test_default_phase_plan_no_warning_when_every_persona_succeeds(capsys):
    """No stderr WARNING is printed when every Plan-phase persona (both
    groups) succeeds."""
    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_recorder([])
    ):
        await orch._default_phase_plan(
            "add a login form", {"size": "standard"}, research_state={}, skip_llm=True
        )

    assert "WARNING: Plan persona dispatch failed" not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_default_phase_plan_warns_on_failed_core_persona(capsys):
    """A failed core-trio persona ("architect") is named in a single stderr
    WARNING line."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if personas == list(orch.PLAN_CORE_PERSONAS):
            return [
                {"persona": "product-manager", "status": "success"},
                {"persona": "architect", "status": "failed", "error": "llm_unavailable"},
                {"persona": "qa-engineer", "status": "success"},
            ]
        return [{"persona": p, "status": "success"} for p in personas]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        await orch._default_phase_plan(
            "add a login form", {"size": "standard"}, research_state={}, skip_llm=True
        )

    stderr = capsys.readouterr().err
    assert stderr.count("WARNING: Plan persona dispatch failed") == 1
    assert "architect" in stderr


@pytest.mark.asyncio
async def test_default_phase_plan_warns_on_failed_critic_persona_only(capsys):
    """A failed critic-only persona (core trio all succeeds) is named in a
    single stderr WARNING line."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if personas == orch.DEFAULT_PERSONAS:
            return [
                {"persona": p, "status": "failed" if p == "plan-review-ux" else "success"}
                for p in personas
            ]
        return [{"persona": p, "status": "success"} for p in personas]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        await orch._default_phase_plan(
            "add a login form", {"size": "standard"}, research_state={}, skip_llm=True
        )

    stderr = capsys.readouterr().err
    assert stderr.count("WARNING: Plan persona dispatch failed") == 1
    assert "plan-review-ux" in stderr


@pytest.mark.asyncio
async def test_default_phase_plan_warns_once_naming_both_a_core_and_a_critic_failure(capsys):
    """A failed core persona ("architect") and a failed critic persona
    ("plan-review-ux") are both named in the SAME single stderr WARNING
    line — not one line per group."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if personas == list(orch.PLAN_CORE_PERSONAS):
            return [
                {"persona": p, "status": "failed" if p == "architect" else "success"}
                for p in personas
            ]
        return [
            {"persona": p, "status": "failed" if p == "plan-review-ux" else "success"}
            for p in personas
        ]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        await orch._default_phase_plan(
            "add a login form", {"size": "standard"}, research_state={}, skip_llm=True
        )

    stderr = capsys.readouterr().err
    assert stderr.count("WARNING: Plan persona dispatch failed") == 1
    assert "architect" in stderr
    assert "plan-review-ux" in stderr


@pytest.mark.asyncio
async def test_default_phase_plan_forwards_skip_llm_false_to_both_dispatch_calls():
    """skip_llm=False must be forwarded verbatim to both dispatch_personas
    calls (core trio and critics) and recorded verbatim in the persisted
    "skip_llm" key."""
    calls = []

    with patch.object(
        orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_recorder(calls)
    ):
        result = await orch._default_phase_plan(
            "add a login form", {"size": "standard"}, research_state={}, skip_llm=False
        )

    assert len(calls) == 2
    assert calls[0]["skip_llm"] is False
    assert calls[1]["skip_llm"] is False
    assert result["skip_llm"] is False


# ---------------------------------------------------------------------------
# Step 1.2 — run_pipeline wiring: phase_plan_fn / orchestrator-plan.json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pipeline_writes_plan_state_for_standard_task():
    """A standard-classified task must write orchestrator-plan.json with the
    exact ordered core_personas and critic_personas lists, one success
    result per persona, and critics_skipped_reason None."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("plan", memory_dir)

    assert exit_code == 0
    assert state["core_personas"] == list(orch.PLAN_CORE_PERSONAS)
    assert state["critic_personas"] == orch.DEFAULT_PERSONAS
    assert len(state["core_results"]) == len(orch.PLAN_CORE_PERSONAS)
    assert len(state["critic_results"]) == len(orch.DEFAULT_PERSONAS)
    assert all(r["status"] == "success" for r in state["core_results"])
    assert all(r["status"] == "success" for r in state["critic_results"])
    assert state["critics_skipped_reason"] is None


@pytest.mark.asyncio
async def test_run_pipeline_writes_plan_state_for_complex_task():
    """A complex-classified task dispatches the identical Plan-phase
    personas — the only branch point in run_pipeline is the trivial fast
    path."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="redesign the payment pipeline",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "complex"},
        )
        state = orch.read_progress("plan", memory_dir)

    assert exit_code == 0
    assert state["core_personas"] == list(orch.PLAN_CORE_PERSONAS)
    assert state["critic_personas"] == orch.DEFAULT_PERSONAS


@pytest.mark.asyncio
async def test_run_pipeline_trivial_task_never_writes_plan_state():
    """A trivial-classified task must never write orchestrator-plan.json."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="fix a typo",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "trivial"},
        )
        state = orch.read_progress("plan", memory_dir)

    assert exit_code == 0
    assert state is None


# ---------------------------------------------------------------------------
# Step 1.2 — --resume: full resume (Plan state exists) and partial resume
# (Research done, Plan pending)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_with_existing_plan_state_skips_plan_dispatch_entirely():
    """--resume with an existing orchestrator-plan.json (and an existing
    orchestrator-research.json) must skip Plan-phase dispatch entirely:
    dispatch_personas is not called at all, and orchestrator-plan.json is
    byte-identical to its pre-run contents. Asserted via call-count, not
    just content equality — deterministic skip_llm=True stub output means a
    broken resume guard that redundantly re-dispatches would still produce
    byte-identical content.

    Scoped to Plan alone via a no-op phase_implement_fn stub: no
    orchestrator-implement.json is pre-seeded here, so without the stub the
    real Implement phase would also call the unconfigured dispatch_personas
    mock and break this test's assert_not_called()."""

    async def noop_phase_implement_fn(request, task, plan_state, skip_llm):
        return {"stub": "implement"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        orch.write_progress(
            "research", {"personas": [], "results": [], "skip_llm": True}, memory_dir
        )
        prior_plan_state = {
            "core_personas": list(orch.PLAN_CORE_PERSONAS),
            "core_results": [],
            "critic_personas": orch.DEFAULT_PERSONAS,
            "critic_results": [],
            "critics_skipped_reason": None,
            "skip_llm": True,
        }
        orch.write_progress("plan", prior_plan_state, memory_dir)
        pre_run_contents = orch.phase_state_path("plan", memory_dir).read_text()

        with patch.object(orch, "dispatch_personas") as mock_dispatch:
            exit_code = await orch.run_pipeline(
                request="add a login form",
                memory_dir=memory_dir,
                skip_llm=True,
                resume=True,
                classify_fn=lambda req: {"size": "standard"},
                phase_implement_fn=noop_phase_implement_fn,
            )

        post_run_contents = orch.phase_state_path("plan", memory_dir).read_text()

    assert exit_code == 0
    mock_dispatch.assert_not_called()
    assert post_run_contents == pre_run_contents


@pytest.mark.asyncio
async def test_resume_with_research_done_dispatches_plan_using_resumed_research_state():
    """--resume with an existing orchestrator-research.json but no
    orchestrator-plan.json yet must dispatch Plan-phase fresh, using the
    disk-read Research state — not a freshly re-dispatched one — as the
    core trio's "research" payload value. dispatch_personas must not have
    been called with RESEARCH_PERSONAS during this run (Research itself
    stays skipped; only Plan dispatches).

    Scoped to Plan alone via a no-op phase_implement_fn stub: no
    orchestrator-implement.json is pre-seeded either, so without the stub
    the real Implement phase would also dispatch through this same fake and
    inflate `calls` beyond the two Plan-phase dispatches this test asserts
    on."""
    calls = []
    prior_research_state = {
        "personas": ["codebase-recon", "architect", "data-flow-tracer"],
        "results": [{"persona": "codebase-recon", "status": "success"}],
        "skip_llm": True,
    }

    async def noop_phase_implement_fn(request, task, plan_state, skip_llm):
        return {"stub": "implement"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        orch.write_progress("research", prior_research_state, memory_dir)

        with patch.object(
            orch,
            "dispatch_personas",
            side_effect=_capturing_dispatch_personas_recorder(calls),
        ):
            exit_code = await orch.run_pipeline(
                request="add a login form",
                memory_dir=memory_dir,
                skip_llm=True,
                resume=True,
                classify_fn=lambda req: {"size": "standard"},
                phase_implement_fn=noop_phase_implement_fn,
            )

        plan_state = orch.read_progress("plan", memory_dir)

    assert exit_code == 0
    assert not any(call["personas"] == list(orch.RESEARCH_PERSONAS) for call in calls)
    assert len(calls) == 2, "Plan phase must dispatch (core trio + critics)"
    assert calls[0]["plan"]["research"] == prior_research_state
    assert plan_state is not None


@pytest.mark.asyncio
async def test_stub_phase_plan_fn_is_honored_end_to_end_through_run_pipeline():
    """A stub phase_plan_fn returning a fixed sentinel result dict must have
    that exact sentinel written to orchestrator-plan.json — mirroring the
    existing stub_research-through-run_pipeline test pattern. skip_llm=True
    is also passed so the Research phase (only phase_plan_fn is stubbed
    here) never risks a live claude CLI call in this test."""
    sentinel = {"sentinel": "plan-result", "core_results": [], "critic_results": []}

    async def stub_plan(request, task, research_state, skip_llm):
        return sentinel

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_plan_fn=stub_plan,
        )
        state = orch.read_progress("plan", memory_dir)

    assert exit_code == 0
    assert state == sentinel


# ---------------------------------------------------------------------------
# Step 1.2 — --dispatch-personas debug branch: plan payload now includes request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_personas_flag_plan_payload_includes_task_and_request():
    """The --dispatch-personas CLI debug branch's plan payload must have
    both a "task" key and a "request" key (closes follow-up #1716's note),
    matching the convention established by the Plan phase's own real
    dispatch calls."""
    calls = []

    with (
        patch.object(
            orch, "dispatch_personas", side_effect=_capturing_dispatch_personas_recorder(calls)
        ),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            dispatch_personas_flag=True,
        )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["plan"]["task"] == {"size": "standard"}
    assert calls[0]["plan"]["request"] == "add a login form"


@pytest.mark.asyncio
async def test_skip_llm_true_plan_results_have_no_output_or_review_status_field():
    """--skip-llm short-circuits Plan dispatch with no live CLI output: each
    entry in both core_results and critic_results has status "success" with
    no "output" or "review_status" field, and orchestrator-plan.json's
    "skip_llm" key is exactly True."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("plan", memory_dir)

    assert exit_code == 0
    for r in state["core_results"] + state["critic_results"]:
        assert r["status"] == "success"
        assert "output" not in r
        assert "review_status" not in r
    assert state["skip_llm"] is True


# ---------------------------------------------------------------------------
# Step 1.2 — _default_phase_implement() unit tests (direct calls, fakes for
# dispatch_persona / dispatch_personas)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_phase_implement_wave_payload_has_task_request_and_plan():
    """The wave dispatch_personas call's plan payload must be
    {"task": task, "request": request, "plan_state": plan_state}, checked
    directly on the call arguments."""
    calls = []

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        calls.append({"personas": list(personas), "plan": plan, "skip_llm": skip_llm})
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    task = {"size": "standard"}
    plan_state = {"core_results": []}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
    ):
        await orch._default_phase_implement(
            "add a login form", task, plan_state, skip_llm=True
        )

    wave_call = calls[0]
    assert wave_call["personas"] == [orch.SOFTWARE_ENGINEER_PERSONA]
    assert wave_call["plan"] == {
        "task": task,
        "request": "add a login form",
        "plan_state": plan_state,
    }
    assert wave_call["skip_llm"] is True


@pytest.mark.asyncio
async def test_default_phase_implement_verification_payload_has_task_request_and_implement_results():
    """The post-success CODE_REVIEW_PANEL and tech-writer dispatch_personas
    calls' plan payloads must each be exactly
    {"task": task, "request": request, "implement_results": results} — where
    "results" is the wave dispatch's own returned results list. Previously
    only the wave's own payload shape was asserted anywhere in this file."""
    calls = []

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        calls.append({"personas": list(personas), "plan": plan})
        return [{"persona": p, "status": "success"} for p in personas]

    task = {"size": "standard"}
    plan_state = {"core_results": []}

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        result = await orch._default_phase_implement(
            "add a login form", task, plan_state, skip_llm=True
        )

    expected_payload = {
        "task": task,
        "request": "add a login form",
        "implement_results": result["results"],
    }
    panel_call = next(c for c in calls if c["personas"] == list(orch.CODE_REVIEW_PANEL))
    tech_writer_call = next(c for c in calls if c["personas"] == [orch.TECH_WRITER_PERSONA])
    assert panel_call["plan"] == expected_payload
    assert tech_writer_call["plan"] == expected_payload


@pytest.mark.asyncio
async def test_default_phase_implement_results_carry_slice_key():
    """Each wave result must have its "slice" key set (matching its
    position in wave_slices) before reconcile() runs — reconcile() indexes
    r["slice"] directly, not via .get."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
    ):
        result = await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=True
        )

    assert result["results"] == [
        {"persona": "software-engineer", "status": "success", "slice": "implement-1"}
    ]


@pytest.mark.asyncio
async def test_default_phase_implement_failed_wave_raises_wave_error_and_skips_review():
    """A failed wave slice must raise WaveError with failing_slice ==
    "implement-1" and must never reach the review-panel/tech-writer
    dispatch calls. Both post-wave dispatches (CODE_REVIEW_PANEL and
    TECH_WRITER_PERSONA) go through dispatch_personas, so a single
    unconditional "any non-wave call" branch in the fake below catches
    either — no separate dispatch_persona fake is needed or reachable,
    since dispatch_persona is only ever called from inside the real
    dispatch_personas, which is fully replaced here."""
    post_wave_calls = []

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if list(personas) == [orch.SOFTWARE_ENGINEER_PERSONA]:
            return [
                {
                    "persona": "software-engineer",
                    "status": "failed",
                    "error": "llm_unavailable",
                }
            ]
        post_wave_calls.append(list(personas))
        return [{"persona": p, "status": "success"} for p in personas]

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        pytest.raises(orch.WaveError) as exc_info,
    ):
        await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=True
        )

    assert exc_info.value.failing_slice == "implement-1"
    assert post_wave_calls == []


@pytest.mark.asyncio
async def test_default_phase_implement_wave_exception_converted_to_dispatch_exception_and_raises():
    """An exception raised by dispatch_persona during the wave call is
    converted, via dispatch_personas' own real return_exceptions=True gather
    normalization (reused, not re-derived — dispatch_personas itself is NOT
    patched here), to a "dispatch_exception" failure stub that still
    carries the correct "slice" key and still raises WaveError."""
    captured = {}
    real_reconcile = orch.reconcile

    async def spying_reconcile(results, wave_slices):
        captured["results"] = results
        await real_reconcile(results, wave_slices)

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        raise RuntimeError("boom")

    with (
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
        patch.object(orch, "reconcile", side_effect=spying_reconcile),
        pytest.raises(orch.WaveError) as exc_info,
    ):
        await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=False
        )

    assert exc_info.value.failing_slice == "implement-1"
    assert captured["results"] == [
        {
            "persona": "software-engineer",
            "status": "failed",
            "error": "dispatch_exception",
            "slice": "implement-1",
        }
    ]


@pytest.mark.asyncio
async def test_default_phase_implement_successful_wave_dispatches_in_order():
    """A successful wave must dispatch_personas([SOFTWARE_ENGINEER_PERSONA]) then
    dispatch_personas(CODE_REVIEW_PANEL) then
    dispatch_personas([TECH_WRITER_PERSONA]), in that order — tech-writer
    goes through dispatch_personas (plural), not a bare dispatch_persona
    call, per _dispatch_implement_verification."""
    call_order = []

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        call_order.append(("dispatch_personas", list(personas)))
        return [{"persona": p, "status": "success"} for p in personas]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=True
        )

    assert call_order == [
        ("dispatch_personas", [orch.SOFTWARE_ENGINEER_PERSONA]),
        ("dispatch_personas", list(orch.CODE_REVIEW_PANEL)),
        ("dispatch_personas", [orch.TECH_WRITER_PERSONA]),
    ]


@pytest.mark.asyncio
async def test_default_phase_implement_failed_review_panel_persona_warns_and_is_recorded(
    capsys,
):
    """A failed review-panel entry (via the dispatch_personas fake) must
    trigger the second, independent _warn_on_failed_personas("Implement
    review", ...) call and still be recorded verbatim in review_results."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if list(personas) == [orch.SOFTWARE_ENGINEER_PERSONA]:
            return [{"persona": "software-engineer", "status": "success"}]
        return [
            {"persona": p, "status": "failed" if p == "arch-review" else "success"}
            for p in personas
        ]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
    ):
        result = await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=True
        )

    stderr = capsys.readouterr().err
    assert (
        "WARNING: Implement review persona dispatch failed (recorded, non-fatal): arch-review"
        in stderr
    )
    assert any(
        r["persona"] == "arch-review" and r["status"] == "failed"
        for r in result["review_results"]
    )


@pytest.mark.asyncio
async def test_default_phase_implement_failed_tech_writer_warns_and_is_recorded(capsys):
    """A failed tech-writer dispatch (via the dispatch_personas fake) must
    trigger the second, independent _warn_on_failed_personas("Implement
    review", ...) call and still be recorded verbatim as tech_writer_result."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if list(personas) == [orch.TECH_WRITER_PERSONA]:
            return [
                {
                    "persona": "tech-writer",
                    "status": "failed",
                    "error": "llm_unavailable",
                }
            ]
        return [{"persona": p, "status": "success"} for p in personas]

    with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
        result = await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=True
        )

    stderr = capsys.readouterr().err
    assert (
        "WARNING: Implement review persona dispatch failed (recorded, non-fatal): tech-writer"
        in stderr
    )
    assert result["tech_writer_result"]["status"] == "failed"


@pytest.mark.asyncio
async def test_default_phase_implement_no_warning_when_all_succeed(capsys):
    """No WARNING of either label ("Implement" or "Implement review") fires
    when every dispatch across both groups succeeds."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
    ):
        await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=True
        )

    stderr = capsys.readouterr().err
    assert "WARNING: Implement persona dispatch failed" not in stderr
    assert "WARNING: Implement review persona dispatch failed" not in stderr


@pytest.mark.asyncio
async def test_default_phase_implement_returns_expected_persisted_shape():
    """_default_phase_implement's return value must have exactly the
    persisted shape: wave_slices, results, review_personas, review_results,
    tech_writer_result, skip_llm."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
    ):
        result = await orch._default_phase_implement(
            "add a login form", {"size": "standard"}, {}, skip_llm=True
        )

    assert set(result.keys()) == {
        "wave_slices",
        "results",
        "review_personas",
        "review_results",
        "tech_writer_result",
        "skip_llm",
    }
    assert result["wave_slices"] == ["implement-1"]
    assert result["review_personas"] == list(orch.CODE_REVIEW_PANEL)
    assert result["review_personas"] is not orch.CODE_REVIEW_PANEL
    assert result["skip_llm"] is True


# ---------------------------------------------------------------------------
# Step 1.2 — run_pipeline wiring: phase_implement_fn / orchestrator-implement.json
# (translating the plan's Gherkin scenario block into real pytest tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pipeline_standard_task_writes_implement_state():
    """Standard-classified task dispatches the Implement-phase wave after
    Plan, matching the Gherkin scenario's exact observables."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("implement", memory_dir)

    assert exit_code == 0
    assert state["wave_slices"] == ["implement-1"]
    assert len(state["results"]) == 1
    assert state["results"][0]["status"] == "success"
    assert state["results"][0]["slice"] == "implement-1"
    assert state["review_personas"] == list(orch.CODE_REVIEW_PANEL)
    assert len(state["review_results"]) == len(orch.CODE_REVIEW_PANEL)
    assert all(r["status"] == "success" for r in state["review_results"])
    assert state["tech_writer_result"]["status"] == "success"


@pytest.mark.asyncio
async def test_run_pipeline_complex_task_dispatches_same_implement_wave():
    """Complex-classified task dispatches the identical single-slice
    Implement-phase wave — the only branch point in run_pipeline is the
    trivial fast-path."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="redesign the payment pipeline",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "complex"},
        )
        state = orch.read_progress("implement", memory_dir)

    assert exit_code == 0
    assert state["wave_slices"] == ["implement-1"]


@pytest.mark.asyncio
async def test_run_pipeline_trivial_task_never_writes_implement_state():
    """Trivial-classified task never reaches the Implement phase: no
    orchestrator-implement.json file is written and exit code is 0 — also
    re-verifying dispatch_personas/dispatch_persona are never called at all
    (Research and Plan are skipped too, not just Implement)."""
    with (
        patch.object(orch, "dispatch_personas") as mock_dispatch_personas,
        patch.object(orch, "dispatch_persona") as mock_dispatch_persona,
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="fix a typo",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "trivial"},
        )
        state = orch.read_progress("implement", memory_dir)

    assert exit_code == 0
    mock_dispatch_personas.assert_not_called()
    mock_dispatch_persona.assert_not_called()
    assert state is None


@pytest.mark.asyncio
async def test_run_pipeline_implement_wave_payload_carries_plan_phase_state():
    """The Implement-phase dispatch receives the Plan phase's aggregated
    state: the software-engineer call's plan payload has a "plan_state" key
    equal to the written orchestrator-plan.json contents, and "task"/
    "request" keys matching the classified task dict and request text."""
    calls = []

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        calls.append({"personas": list(personas), "plan": plan})
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    task = {"size": "standard"}
    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: task,
        )
        plan_state = orch.read_progress("plan", memory_dir)

    assert exit_code == 0
    wave_call = next(c for c in calls if c["personas"] == [orch.SOFTWARE_ENGINEER_PERSONA])
    assert wave_call["plan"]["plan_state"] == plan_state
    assert wave_call["plan"]["task"] == task
    assert wave_call["plan"]["request"] == "add a login form"


@pytest.mark.asyncio
async def test_run_pipeline_failed_wave_slice_warning_precedes_error_and_skips_review(
    capsys,
):
    """A failed wave slice's WARNING prints before WaveError turns into exit
    code 1: the WARNING appears exactly once and before the ERROR line,
    stderr contains "Resume with:", exit code is 1, no
    orchestrator-implement.json file is written, and the review panel and
    tech-writer are never dispatched. This test runs the full pipeline
    (Research and Plan dispatch for real, through this same fake), so the
    post-wave tracking below matches only the two known post-wave rosters
    (CODE_REVIEW_PANEL, [TECH_WRITER_PERSONA]) rather than any non-wave
    call — both go through dispatch_personas, so this one check catches
    either; no separate dispatch_persona fake is reachable, since it is
    only ever called from inside the real dispatch_personas, which is
    fully replaced here."""
    post_wave_calls = []
    post_wave_rosters = (list(orch.CODE_REVIEW_PANEL), [orch.TECH_WRITER_PERSONA])

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if list(personas) == [orch.SOFTWARE_ENGINEER_PERSONA]:
            return [
                {
                    "persona": "software-engineer",
                    "status": "failed",
                    "error": "llm_unavailable",
                }
            ]
        if list(personas) in post_wave_rosters:
            post_wave_calls.append(list(personas))
        return [{"persona": p, "status": "success"} for p in personas]

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("implement", memory_dir)

    stderr = capsys.readouterr().err
    warning_marker = (
        "WARNING: Implement persona dispatch failed (wave barrier will fail): "
        "software-engineer"
    )
    error_marker = "ERROR: wave barrier failed on slice 'implement-1'"
    assert stderr.count(warning_marker) == 1
    assert error_marker in stderr
    assert stderr.index(warning_marker) < stderr.index(error_marker)
    assert "Resume with:" in stderr
    assert exit_code == 1
    assert state is None
    assert post_wave_calls == []


@pytest.mark.asyncio
async def test_run_pipeline_wave_dispatch_exception_results_in_wave_error_exit_1(
    capsys,
):
    """An exception raised during the wave dispatch is converted to a
    dispatch_exception failure by dispatch_personas' own real
    return_exceptions=True normalization, then reaches reconcile() like any
    other failed slice — stderr shows the ERROR message, exit code is 1, and
    no orchestrator-implement.json file is written.

    ASSUMPTION (recorded per this repo's convention of naming under-specified
    plan details explicitly rather than resolving them silently): the plan's
    Gherkin literally says "a fake dispatch_personas that raises RuntimeError
    for the software-engineer call". Patching dispatch_personas itself
    wholesale to raise would propagate the RuntimeError straight out of
    _default_phase_implement's `results = await dispatch_personas(...)` line
    uncaught — past run_pipeline's `except WaveError` (which only catches
    WaveError, not a bare RuntimeError) — contradicting the scenario's own
    stated observable (stderr's ERROR message, exit code 1). Patching
    dispatch_persona instead (leaving the real, unpatched dispatch_personas'
    gather/return_exceptions=True path intact, exactly as the plan's own
    "(the dispatch_exception status value itself is asserted at the
    _default_phase_implement unit-test level...)" parenthetical describes)
    is the only wiring that produces the scenario's literal stated outcome.

    Scoped to Implement alone via no-op phase_research_fn/phase_plan_fn
    stubs — matching the established convention elsewhere in this file
    (e.g. test_default_phase_research_records_one_failed_persona_verbatim_without_raising):
    without them, this same globally-raising dispatch_persona patch would
    also fail every Research and Plan persona dispatch, which is unrelated
    to what this test verifies."""

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        raise RuntimeError("boom")

    async def noop_phase_research_fn(request, task, skip_llm):
        return {"stub": "research"}

    async def noop_phase_plan_fn(request, task, research_state, skip_llm):
        return {"stub": "plan"}

    with (
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_research_fn=noop_phase_research_fn,
            phase_plan_fn=noop_phase_plan_fn,
        )
        state = orch.read_progress("implement", memory_dir)

    stderr = capsys.readouterr().err
    assert "ERROR: wave barrier failed on slice 'implement-1'" in stderr
    assert exit_code == 1
    assert state is None


@pytest.mark.asyncio
async def test_run_pipeline_resume_retries_implement_from_scratch_after_wave_error():
    """--resume retries the Implement phase from scratch after a real
    WaveError failure: the first run exits 1 with no orchestrator-
    implement.json written; a second run with --resume re-dispatches
    software-engineer (not a skip) and succeeds, proving the uncaught-
    WaveError-propagation design's real payoff — a failed wave leaves no
    trace for _run_phase to find."""
    call_count = {"n": 0}

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if list(personas) == [orch.SOFTWARE_ENGINEER_PERSONA]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [
                    {
                        "persona": "software-engineer",
                        "status": "failed",
                        "error": "llm_unavailable",
                    }
                ]
            return [{"persona": "software-engineer", "status": "success"}]
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code_1 = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state_after_failure = orch.read_progress("implement", memory_dir)

        exit_code_2 = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            resume=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state_after_resume = orch.read_progress("implement", memory_dir)

    assert exit_code_1 == 1
    assert state_after_failure is None
    assert call_count["n"] == 2, "dispatch_personas must be called again for software-engineer"
    assert exit_code_2 == 0
    assert state_after_resume["results"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_run_pipeline_successful_wave_dispatches_engineer_then_panel_then_tech_writer_in_order():
    """A successful wave dispatches software-engineer, then the code-review
    panel, then tech-writer, in that order — verified end-to-end through
    run_pipeline via a dependency-injected fake that records call order.
    tech-writer is dispatched via dispatch_personas (plural), not a bare
    dispatch_persona call — see _dispatch_implement_verification."""
    call_order = []

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        call_order.append(("dispatch_personas", list(personas)))
        return [{"persona": p, "status": "success"} for p in personas]

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )

    assert exit_code == 0
    wave_index = call_order.index(("dispatch_personas", [orch.SOFTWARE_ENGINEER_PERSONA]))
    panel_index = call_order.index(("dispatch_personas", list(orch.CODE_REVIEW_PANEL)))
    tech_writer_index = call_order.index(("dispatch_personas", [orch.TECH_WRITER_PERSONA]))
    assert wave_index < panel_index < tech_writer_index


@pytest.mark.asyncio
async def test_run_pipeline_failed_review_panel_persona_is_recorded_non_fatal(capsys):
    """A failed review-panel persona is recorded, non-fatal, with its own
    warning: stderr contains the Implement-review WARNING for "arch-review",
    exit code is 0, and orchestrator-implement.json's "review_results"
    contains a status "failed" entry for "arch-review"."""

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        if list(personas) == [orch.SOFTWARE_ENGINEER_PERSONA]:
            return [{"persona": "software-engineer", "status": "success"}]
        if list(personas) == list(orch.CODE_REVIEW_PANEL):
            return [
                {"persona": p, "status": "failed" if p == "arch-review" else "success"}
                for p in personas
            ]
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("implement", memory_dir)

    stderr = capsys.readouterr().err
    assert (
        "WARNING: Implement review persona dispatch failed (recorded, non-fatal): arch-review"
        in stderr
    )
    assert exit_code == 0
    assert any(
        r["persona"] == "arch-review" and r["status"] == "failed"
        for r in state["review_results"]
    )


@pytest.mark.asyncio
async def test_run_pipeline_failed_tech_writer_is_recorded_non_fatal(capsys):
    """A failed tech-writer dispatch is recorded, non-fatal, with its own
    warning: stderr contains the Implement-review WARNING for "tech-writer",
    exit code is 0, and orchestrator-implement.json's "tech_writer_result"
    has status "failed". The fake dispatch_persona only fails for
    "tech-writer" (not every persona) since dispatch_persona is also the
    function the real dispatch_personas calls internally for Research,
    Plan, and the wave/review-panel dispatches in this same run — failing
    universally would break those groups too."""

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        if persona == orch.TECH_WRITER_PERSONA:
            return {"persona": persona, "status": "failed", "error": "llm_unavailable"}
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("implement", memory_dir)

    stderr = capsys.readouterr().err
    assert (
        "WARNING: Implement review persona dispatch failed (recorded, non-fatal): tech-writer"
        in stderr
    )
    assert exit_code == 0
    assert state["tech_writer_result"]["status"] == "failed"


@pytest.mark.asyncio
async def test_run_pipeline_no_implement_warning_when_all_dispatches_succeed(capsys):
    """No Implement WARNING is printed when every dispatch in both groups
    succeeds."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )

    assert exit_code == 0
    stderr = capsys.readouterr().err
    assert "WARNING: Implement persona dispatch failed" not in stderr
    assert "WARNING: Implement review persona dispatch failed" not in stderr


@pytest.mark.asyncio
async def test_run_pipeline_skip_llm_true_implement_state_has_no_output_or_review_status_fields():
    """--skip-llm short-circuits Implement dispatch with no live CLI output:
    each entry in "results", "review_results", and "tech_writer_result" has
    status "success" with no "output" or "review_status" field, and
    orchestrator-implement.json's "skip_llm" key is exactly True."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("implement", memory_dir)

    assert exit_code == 0
    for r in state["results"] + state["review_results"] + [state["tech_writer_result"]]:
        assert r["status"] == "success"
        assert "output" not in r
        assert "review_status" not in r
    assert state["skip_llm"] is True


@pytest.mark.asyncio
async def test_run_pipeline_skip_llm_false_is_forwarded_to_every_implement_dispatch_call():
    """skip_llm=False is forwarded to every Implement-phase dispatch call
    (dependency-injected fakes for both dispatch_persona and
    dispatch_personas; no live CLI call is made) and recorded verbatim in
    the persisted "skip_llm" key."""
    skip_llm_values = []

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        skip_llm_values.append(skip_llm)
        return [{"persona": p, "status": "success"} for p in personas]

    async def fake_dispatch_persona(persona, plan, skip_llm=False):
        skip_llm_values.append(skip_llm)
        return {"persona": persona, "status": "success"}

    with (
        patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas),
        patch.object(orch, "dispatch_persona", side_effect=fake_dispatch_persona),
        tempfile.TemporaryDirectory() as tmp,
    ):
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=False,
            classify_fn=lambda req: {"size": "standard"},
        )
        state = orch.read_progress("implement", memory_dir)

    assert exit_code == 0
    assert all(v is False for v in skip_llm_values)
    assert state["skip_llm"] is False


@pytest.mark.asyncio
async def test_resume_with_existing_implement_state_skips_implement_dispatch_entirely():
    """--resume with existing orchestrator-research.json,
    orchestrator-plan.json, and orchestrator-implement.json already present
    skips Implement-phase dispatch entirely: neither dispatch_persona nor
    dispatch_personas is called, and orchestrator-implement.json is
    byte-identical to its pre-run contents. Re-verified against the real
    (non-stub) _default_phase_implement, asserting on call count directly —
    not just output-content equality — mirroring the Slice 3 precedent for
    why content equality alone cannot prove a resume guard fired under
    deterministic --skip-llm stub output."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        orch.write_progress(
            "research", {"personas": [], "results": [], "skip_llm": True}, memory_dir
        )
        orch.write_progress(
            "plan",
            {
                "core_personas": list(orch.PLAN_CORE_PERSONAS),
                "core_results": [],
                "critic_personas": orch.DEFAULT_PERSONAS,
                "critic_results": [],
                "critics_skipped_reason": None,
                "skip_llm": True,
            },
            memory_dir,
        )
        prior_implement_state = {
            "wave_slices": ["implement-1"],
            "results": [
                {"persona": "software-engineer", "status": "success", "slice": "implement-1"}
            ],
            "review_personas": list(orch.CODE_REVIEW_PANEL),
            "review_results": [
                {"persona": p, "status": "success"} for p in orch.CODE_REVIEW_PANEL
            ],
            "tech_writer_result": {"persona": "tech-writer", "status": "success"},
            "skip_llm": True,
        }
        orch.write_progress("implement", prior_implement_state, memory_dir)
        pre_run_contents = orch.phase_state_path("implement", memory_dir).read_text()

        with (
            patch.object(orch, "dispatch_personas") as mock_dispatch_personas,
            patch.object(orch, "dispatch_persona") as mock_dispatch_persona,
        ):
            exit_code = await orch.run_pipeline(
                request="add a login form",
                memory_dir=memory_dir,
                skip_llm=True,
                resume=True,
                classify_fn=lambda req: {"size": "standard"},
            )

        post_run_contents = orch.phase_state_path("implement", memory_dir).read_text()

    assert exit_code == 0
    mock_dispatch_personas.assert_not_called()
    mock_dispatch_persona.assert_not_called()
    assert post_run_contents == pre_run_contents


@pytest.mark.asyncio
async def test_resume_with_plan_done_dispatches_implement_using_resumed_plan_state():
    """--resume with Plan done but Implement pending dispatches Implement
    using the resumed plan state: the software-engineer call's plan
    payload's "plan_state" key equals the existing orchestrator-plan.json
    contents (not a freshly re-dispatched one), and orchestrator-implement.json
    is written. Re-verified against the real (non-stub) _default_phase_implement,
    asserting on dispatch_personas' call count directly (the tech-writer
    call, dispatched via dispatch_personas, plural) — not just
    output-content equality."""
    calls = []
    prior_plan_state = {
        "core_personas": list(orch.PLAN_CORE_PERSONAS),
        "core_results": [{"persona": "product-manager", "status": "success"}],
        "critic_personas": orch.DEFAULT_PERSONAS,
        "critic_results": [],
        "critics_skipped_reason": None,
        "skip_llm": True,
    }

    async def fake_dispatch_personas(personas, plan, skip_llm=False):
        calls.append({"personas": list(personas), "plan": plan})
        return [{"persona": p, "status": "success"} for p in personas]

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        orch.write_progress(
            "research", {"personas": [], "results": [], "skip_llm": True}, memory_dir
        )
        orch.write_progress("plan", prior_plan_state, memory_dir)

        with patch.object(orch, "dispatch_personas", side_effect=fake_dispatch_personas):
            exit_code = await orch.run_pipeline(
                request="add a login form",
                memory_dir=memory_dir,
                skip_llm=True,
                resume=True,
                classify_fn=lambda req: {"size": "standard"},
            )

        implement_state = orch.read_progress("implement", memory_dir)

    assert exit_code == 0
    wave_call = next(c for c in calls if c["personas"] == [orch.SOFTWARE_ENGINEER_PERSONA])
    assert wave_call["plan"]["plan_state"] == prior_plan_state
    assert implement_state is not None
    assert any(c["personas"] == [orch.TECH_WRITER_PERSONA] for c in calls)


@pytest.mark.asyncio
async def test_stub_phase_implement_fn_is_honored_end_to_end_through_run_pipeline():
    """A stub phase_implement_fn returning a fixed sentinel result dict must
    have that exact sentinel written to orchestrator-implement.json —
    mirroring the existing stub_research/stub_plan-through-run_pipeline test
    pattern. skip_llm=True is also passed so neither Research nor Plan risks
    a live claude CLI call in this test."""
    sentinel = {"sentinel": "implement-result", "results": [], "review_results": []}

    async def stub_implement(request, task, plan_state, skip_llm):
        return sentinel

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_implement_fn=stub_implement,
        )
        state = orch.read_progress("implement", memory_dir)

    assert exit_code == 0
    assert state == sentinel


@pytest.mark.asyncio
async def test_run_pipeline_wave_error_from_injected_phase_implement_fn_prints_message_and_exits_1(
    capsys,
):
    """A WaveError-raising phase_implement_fn (patched directly, not via the
    real dispatch fakes) results in exit code 1, the two-line stderr
    message, and no orchestrator-implement.json written."""

    async def failing_phase_implement_fn(request, task, plan_state, skip_llm):
        raise orch.WaveError(failing_slice="implement-1", succeeded=[])

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="add a login form",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_implement_fn=failing_phase_implement_fn,
        )
        state = orch.read_progress("implement", memory_dir)

    stderr = capsys.readouterr().err
    assert "ERROR: wave barrier failed on slice 'implement-1'" in stderr
    assert f"Resume with: python3 {orch.SCRIPTS / 'orchestrator.py'} --resume" in stderr
    assert exit_code == 1
    assert state is None
