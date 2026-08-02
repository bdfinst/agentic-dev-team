"""Pytest async tests for plugins/dev-team/scripts/orchestrator.py — Slice 6.

Tests classification, fast-path routing, phase state persistence,
--resume skip logic, persona dispatch concurrency, and wave barrier.
"""

from __future__ import annotations

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
# Step 6.1 — Task classification and fast-path branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_trivial_stub_takes_fast_path():
    """With classify_fn returning trivial, run_pipeline() must NOT call phase functions."""
    called = []

    async def stub_research(task, skip_llm):
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

    async def stub_research(task, skip_llm):
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

    async def stub_research(task, skip_llm):
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

    async def stub_research(task, skip_llm):
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


@pytest.mark.parametrize(
    "persona", ["plan-review-acceptance", "software-engineer"]
)
@pytest.mark.asyncio
async def test_dispatch_persona_malformed_envelope_maps_to_failed_stub(persona):
    """A malformed (non-JSON) top-level --output-format json envelope must
    map to the generalized failure stub, not raise, for both a critic and a
    non-critic persona."""

    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess("not json at all {")

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(persona, plan={}, skip_llm=False)

    assert result == {
        "persona": persona,
        "status": "failed",
        "error": "llm_unavailable",
    }
    assert "verdict" not in result


@pytest.mark.parametrize(
    "persona", ["plan-review-acceptance", "software-engineer"]
)
@pytest.mark.asyncio
async def test_dispatch_persona_non_object_envelope_maps_to_failed_stub(persona):
    """A top-level envelope that is syntactically valid JSON but not a JSON
    object (e.g. a bare array) must degrade to the generalized failure stub,
    not raise AttributeError from envelope.get() on a non-dict, for both a
    critic and a non-critic persona."""

    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess("[1, 2, 3]")

    with patch.object(orch.subprocess, "run", side_effect=fake_run):
        result = await orch.dispatch_persona(persona, plan={}, skip_llm=False)

    assert result == {
        "persona": persona,
        "status": "failed",
        "error": "llm_unavailable",
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
