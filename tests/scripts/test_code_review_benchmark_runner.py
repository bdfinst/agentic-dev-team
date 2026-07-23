"""Unit tests for the #821 benchmark harness's runner.

All dispatch/checkout behavior is injected (no real subprocess, no real
`claude` invocation, no network) — plain dependency injection rather than
patching `subprocess.run` directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

import runner  # noqa: E402

_CASE: Dict[str, Any] = {
    "dataset": "defects4j",
    "project": "Lang",
    "bug_id": "1",
    "language": "java",
    "ground_truth_files": ["src/Foo.java"],
    "ground_truth_hunks": [{"file": "src/Foo.java", "start_line": 10, "end_line": 12}],
    "description": None,
    "extra": {},
}

_REVIEW_JSON = {
    "overall": "warn",
    "agents": [
        {
            "agentName": "correctness-review",
            "status": "warn",
            "issues": [
                {
                    "severity": "error",
                    "confidence": "high",
                    "file": "src/Foo.java",
                    "line": 11,
                    "message": "missing assignment",
                }
            ],
            "summary": "1 issue",
        }
    ],
}


def _seed_checkout(workdir: str, files) -> None:
    for rel in files:
        path = Path(workdir) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub\n", encoding="utf-8")


def _dispatch_result(
    review_json: Dict[str, Any] = _REVIEW_JSON, cost_usd: Any = 4.48
) -> Dict[str, Any]:
    """A dispatch_fn return value shaped like the real `make_isolated_dispatch_fn`
    output: both the raw wrapper stdout AND the already-extracted `result_text`
    (the runner reads `result_text` directly; it does not re-parse `raw_stdout`),
    plus `cost_usd` (#1000) — defaults to a real measured value (#974) so tests
    exercise cost propagation by default rather than opting in."""
    result_text = json.dumps(review_json)
    return {
        "raw_stdout": json.dumps({"result": result_text}),
        "result_text": result_text,
        "cost_usd": cost_usd,
    }


def test_run_case_hit(tmp_path: Path) -> None:
    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        assert "--json" in prompt
        assert os.path.isdir(cwd)
        # Fix-only scope: only the ground-truth file should be present.
        assert (Path(cwd) / "src" / "Foo.java").is_file()
        return _dispatch_result()

    record = runner.run_case(
        _CASE,
        checkout_fn=checkout_fn,
        dispatch_fn=dispatch_fn,
        results_dir=tmp_path,
    )
    assert record["hit"] is True
    assert record["skipped"] is False
    assert len(record["findings"]) == 1
    assert record["unmatched_findings"] == []
    assert Path(record["raw_output_path"]).is_file()
    assert record["cost_usd"] == 4.48


def test_run_case_checkout_failure_is_skipped(tmp_path: Path) -> None:
    record = runner.run_case(
        _CASE,
        checkout_fn=lambda workdir: False,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
    )
    assert record["skipped"] is True
    assert record["reason"] == "checkout failed"
    # No dispatch ever happened for this case — nothing was spent (#1000).
    assert record["cost_usd"] is None


def test_run_case_no_ground_truth_is_skipped(tmp_path: Path) -> None:
    case = dict(_CASE, ground_truth_hunks=[], ground_truth_files=[])
    record = runner.run_case(
        case,
        checkout_fn=lambda workdir: True,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
    )
    assert record["skipped"] is True
    assert record["reason"] == "no ground-truth hunks"


def test_run_case_uses_ground_truth_fn_when_case_has_none(tmp_path: Path) -> None:
    case = dict(_CASE, ground_truth_hunks=[], ground_truth_files=[])

    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def ground_truth_fn(workdir: str):
        return [{"file": "src/Foo.java", "start_line": 10, "end_line": 12}]

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        return _dispatch_result()

    record = runner.run_case(
        case,
        checkout_fn=checkout_fn,
        ground_truth_fn=ground_truth_fn,
        dispatch_fn=dispatch_fn,
        results_dir=tmp_path,
    )
    assert record["skipped"] is False
    assert record["hit"] is True


@pytest.mark.parametrize(
    "language,files",
    [
        pytest.param(
            "javascript",
            ["History.md", "package.json"],
            id="javascript-changelog-and-manifest",
        ),
        pytest.param(
            "java", ["pom.xml", "CHANGES.md"], id="java-build-file-and-changelog"
        ),
    ],
)
def test_run_case_non_source_ground_truth_is_skipped(
    tmp_path: Path, language: str, files: List[str]
) -> None:
    """#965: ground truth touching only non-source files (a changelog entry
    and a package.json/pom.xml, say) must not be scored as a recall miss —
    for every recognized language, not just one."""
    case = dict(
        _CASE,
        language=language,
        ground_truth_hunks=[{"file": f, "start_line": 1, "end_line": 1} for f in files],
        ground_truth_files=files,
    )
    dispatched = []

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        dispatched.append(prompt)
        return _dispatch_result()

    record = runner.run_case(
        case,
        checkout_fn=lambda workdir: True,
        dispatch_fn=dispatch_fn,
        results_dir=tmp_path,
    )
    assert record["skipped"] is True
    assert record["reason"] == "ground truth touches no recognized source files"
    assert dispatched == []


@pytest.mark.parametrize(
    "language,files",
    [
        pytest.param(
            "javascript",
            ["History.md", "lib/foo.js"],
            id="mixed-source-and-nonsource",
        ),
        pytest.param(
            "javascript",
            ["History.md", "lib/foo.jsx"],
            id="non-js-recognized-extension",
        ),
        pytest.param("ruby", ["main.rb"], id="unmapped-language-safe-default"),
    ],
)
def test_run_case_is_scored_when_source_is_touched_or_language_unmapped(
    tmp_path: Path, language: str, files: List[str]
) -> None:
    """Must NOT skip: a non-source file alongside a real source file (only
    ZERO recognized extensions triggers the skip), a non-`.js` recognized
    javascript extension (#965 AC: `.jsx`/`.mjs`/`.cjs` are wired in, not
    just declared), and an unmapped language (safe default so a future
    adapter's cases aren't silently lost to this check)."""
    case = dict(
        _CASE,
        language=language,
        ground_truth_hunks=[{"file": f, "start_line": 1, "end_line": 1} for f in files],
        ground_truth_files=files,
    )
    dispatched = []

    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, files)
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        dispatched.append(prompt)
        return _dispatch_result()

    record = runner.run_case(
        case,
        checkout_fn=checkout_fn,
        dispatch_fn=dispatch_fn,
        results_dir=tmp_path,
    )
    assert record["skipped"] is False
    assert len(dispatched) == 1


def test_touches_recognized_source_boundary_cases() -> None:
    """Direct unit coverage of `_touches_recognized_source()`'s own boundary
    matrix — the `run_case`-level tests above prove the check is actually
    wired into the skip/dispatch decision, not that every extension/language
    combination is correct; that's this test's job."""
    assert runner._touches_recognized_source(["main.rb"], "ruby") is True
    assert runner._touches_recognized_source([], "") is True
    assert runner._touches_recognized_source(["History.md"], "javascript") is False
    assert (
        runner._touches_recognized_source(["History.md", "lib/foo.js"], "javascript")
        is True
    )
    assert runner._touches_recognized_source(["src/Foo.java"], "java") is True
    assert runner._touches_recognized_source(["pom.xml"], "java") is False


def test_run_case_unparseable_json_is_skipped(tmp_path: Path) -> None:
    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        return {
            "raw_stdout": json.dumps({"result": "not json at all"}),
            "result_text": "not json at all",
            "cost_usd": 1.29,
        }

    record = runner.run_case(
        _CASE,
        checkout_fn=checkout_fn,
        dispatch_fn=dispatch_fn,
        results_dir=tmp_path,
    )
    assert record["skipped"] is True
    assert record["reason"] == "unparseable --json output"
    # Raw output is still saved verbatim even on a parse failure.
    assert Path(record["raw_output_path"]).is_file()
    # #1000: the dispatch happened and cost real money even though its
    # output couldn't be parsed/scored — that cost must not be lost.
    assert record["cost_usd"] == 1.29


def test_skip_record_defaults_cost_usd_to_none() -> None:
    """Direct unit coverage: every skip reason that fires before a dispatch
    (the overwhelming majority of call sites) gets `cost_usd=None` for free
    by simply not passing the keyword — this is the contract that makes
    that safe."""
    record = runner.skip_record(_CASE, "checkout failed")
    assert record["cost_usd"] is None


def test_skip_record_carries_explicit_cost_usd() -> None:
    record = runner.skip_record(
        _CASE, "unparseable --json output", "raw.txt", cost_usd=3.33
    )
    assert record["cost_usd"] == 3.33


def test_run_case_full_repo_scope_passes_full_checkout(tmp_path: Path) -> None:
    seen_cwd = {}

    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java", "src/Unrelated.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        seen_cwd["cwd"] = cwd
        assert (Path(cwd) / "src" / "Unrelated.java").is_file()
        return _dispatch_result()

    runner.run_case(
        _CASE,
        checkout_fn=checkout_fn,
        dispatch_fn=dispatch_fn,
        results_dir=tmp_path,
        scope="full-repo",
    )
    assert seen_cwd["cwd"]


def test_run_case_records_test_verification_against_full_checkout(
    tmp_path: Path,
) -> None:
    seen_checkout_dir = {}

    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        return _dispatch_result()

    def test_fn(checkout_dir: str) -> Dict[str, Any]:
        # Called against the full checkout, not the fix-only scoped copy —
        # assert while the checkout dir still exists (run_case tears it
        # down in its `finally` before returning).
        seen_checkout_dir["found_unrelated_file"] = (
            Path(checkout_dir) / "src" / "Foo.java"
        ).is_file()
        return {"configured": True, "ran": True, "reproduced": True}

    record = runner.run_case(
        _CASE,
        checkout_fn=checkout_fn,
        dispatch_fn=dispatch_fn,
        test_fn=test_fn,
        results_dir=tmp_path,
    )
    assert record["test_verification"] == {
        "configured": True,
        "ran": True,
        "reproduced": True,
    }
    assert seen_checkout_dir["found_unrelated_file"] is True


def test_run_case_test_fn_exception_does_not_crash_the_case(tmp_path: Path) -> None:
    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        return _dispatch_result()

    def test_fn(checkout_dir: str) -> Dict[str, Any]:
        raise RuntimeError("boom")

    record = runner.run_case(
        _CASE,
        checkout_fn=checkout_fn,
        dispatch_fn=dispatch_fn,
        test_fn=test_fn,
        results_dir=tmp_path,
    )
    assert record["skipped"] is False
    assert record["test_verification"]["configured"] is False
    assert record["test_verification"]["error"] == "boom"


def test_run_case_test_verification_none_without_test_fn(tmp_path: Path) -> None:
    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        return _dispatch_result()

    record = runner.run_case(
        _CASE, checkout_fn=checkout_fn, dispatch_fn=dispatch_fn, results_dir=tmp_path
    )
    assert record["test_verification"] is None


def test_extract_review_json_handles_markdown_fence() -> None:
    fenced = "```json\n" + json.dumps(_REVIEW_JSON) + "\n```"
    assert runner._extract_review_json(fenced) == _REVIEW_JSON


def test_extract_review_json_none_on_garbage() -> None:
    assert runner._extract_review_json("not json") is None
    assert runner._extract_review_json(None) is None


def test_extract_review_json_handles_preamble_before_fence() -> None:
    """#963: models sometimes narrate before the JSON fence, violating
    the --json contract but not actually losing the payload."""
    narrated = (
        "Emitting the required aggregated JSON per contract "
        "(no file writes, stdout only):\n\n"
        "```json\n" + json.dumps(_REVIEW_JSON) + "\n```"
    )
    assert runner._extract_review_json(narrated) == _REVIEW_JSON


def test_extract_review_json_prefers_last_fence_when_multiple() -> None:
    """If a model emits more than one fenced block, the LAST one is the
    more likely candidate for the real payload."""
    other_json = {"overall": "pass", "agents": []}
    text = (
        "Here's an example of the shape:\n\n"
        "```json\n" + json.dumps(other_json) + "\n```\n\n"
        "Emitting the real result:\n\n"
        "```json\n" + json.dumps(_REVIEW_JSON) + "\n```"
    )
    assert runner._extract_review_json(text) == _REVIEW_JSON


def test_extract_review_json_falls_back_to_earlier_fence_if_last_invalid() -> None:
    """A trailing fence that isn't valid JSON must not shadow an earlier
    valid one."""
    text = (
        "```json\n" + json.dumps(_REVIEW_JSON) + "\n```\n\n"
        "(note: the above is the final answer)\n\n"
        "```\nnot actually json\n```"
    )
    assert runner._extract_review_json(text) == _REVIEW_JSON


def test_extract_review_json_no_fence_parses_raw_json() -> None:
    assert runner._extract_review_json(json.dumps(_REVIEW_JSON)) == _REVIEW_JSON


def _make_fake_isolated_dispatch(tmp_path: Path, calls: list):
    """Shared fake `isolated_dispatch` module stand-in for
    `make_isolated_dispatch_fn()` tests (#957 auth-carry-over, #1000
    cost extraction) — avoids redefining the same four-method stub per test."""

    class _FakeIsolatedDispatch:
        @staticmethod
        def make_cell_home():
            home = tmp_path / "cell-home"
            home.mkdir(exist_ok=True)
            return home

        @staticmethod
        def copy_auth_state(home):
            calls.append(("copy_auth_state", home))
            return True

        @staticmethod
        def new_session_id():
            return "11111111-1111-1111-1111-111111111111"

        @staticmethod
        def build_env(home):
            return {}

        @staticmethod
        def build_cmd(prompt, session_id, model, cwd=None):
            return ["claude", "-p", prompt]

    return _FakeIsolatedDispatch


def test_make_isolated_dispatch_fn_carries_over_auth_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`make_isolated_dispatch_fn()`'s dispatch closure must call
    `copy_auth_state()` (#957) so the harness's own runs keep the
    operator's real Claude Code login — unlike the standalone
    `isolated_dispatch.py` script/skill, where this is opt-in."""
    calls: list = []
    monkeypatch.setattr(
        runner,
        "_load_isolated_dispatch",
        lambda: _make_fake_isolated_dispatch(tmp_path, calls),
    )

    import subprocess as subprocess_module

    def fake_run(cmd, **kwargs):
        return subprocess_module.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps({"result": "{}"})
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    dispatch_fn("/code-review --json", str(tmp_path))

    assert calls == [("copy_auth_state", tmp_path / "cell-home")]


def test_make_isolated_dispatch_fn_extracts_cost_usd_from_wrapper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#1000: the wrapper JSON's `total_cost_usd` (already reported by the
    underlying `claude -p --output-format json` call) must be surfaced as
    `cost_usd` in the dispatch result, so the harness can track real spend."""
    monkeypatch.setattr(
        runner,
        "_load_isolated_dispatch",
        lambda: _make_fake_isolated_dispatch(tmp_path, []),
    )

    import subprocess as subprocess_module

    def fake_run(cmd, **kwargs):
        return subprocess_module.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps({"result": "{}", "total_cost_usd": 2.5}),
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", str(tmp_path))

    assert result["cost_usd"] == 2.5


def test_make_isolated_dispatch_fn_cost_usd_none_when_wrapper_unparseable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A malformed wrapper (or a case where the process was killed before
    printing) must not crash — `cost_usd` is simply `None`, mirroring
    `result_text`'s existing None-on-failure contract."""
    monkeypatch.setattr(
        runner,
        "_load_isolated_dispatch",
        lambda: _make_fake_isolated_dispatch(tmp_path, []),
    )

    import subprocess as subprocess_module

    def fake_run(cmd, **kwargs):
        return subprocess_module.CompletedProcess(
            args=cmd, returncode=0, stdout="not json at all"
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", str(tmp_path))

    assert result["cost_usd"] is None


class _RetryFakeIsolatedDispatch:
    """A `_load_isolated_dispatch()` fake that supports the `resume` kwarg
    `build_cmd()` gained in Slice 1 — the pre-existing
    `_FakeIsolatedDispatch` above predates that and deliberately isn't
    reused here, so this class's `build_cmd` signature exactly matches the
    real `isolated_dispatch.build_cmd`'s post-Slice-1 shape."""

    SESSION_ID = "22222222-2222-2222-2222-222222222222"

    @staticmethod
    def make_cell_home():
        return Path(tempfile.mkdtemp(prefix="crb-retry-fake-home-"))

    @staticmethod
    def copy_auth_state(home):
        return True

    @classmethod
    def new_session_id(cls):
        return cls.SESSION_ID

    @staticmethod
    def build_env(home):
        return {}

    @staticmethod
    def build_cmd(prompt, session_id, model, cwd=None, resume=False):
        cmd = ["claude", "-p", prompt]
        cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
        cmd += ["--output-format", "json", "--model", model]
        return cmd


def _wrapper_stdout(result_text: Optional[str], is_error: bool = False) -> str:
    return json.dumps({"result": result_text, "is_error": is_error})


def test_make_isolated_dispatch_fn_retries_once_on_unparseable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#999/#1002: a completed, non-error dispatch whose result_text has no
    parseable --json payload gets exactly ONE follow-up dispatch, resuming
    the SAME session — not a fresh one — asking it to re-emit the JSON."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            stdout = _wrapper_stdout("Aggregated JSON emitted per contract.")
        else:
            stdout = _wrapper_stdout(json.dumps(_REVIEW_JSON))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 2
    retry_cmd = calls[1]
    assert "--resume" in retry_cmd
    assert (
        retry_cmd[retry_cmd.index("--resume") + 1]
        == _RetryFakeIsolatedDispatch.SESSION_ID
    )
    assert "--session-id" not in retry_cmd
    # The retry sends the short re-emission instruction, NOT a repeat of the
    # original /code-review prompt (which would defeat the "cheap, no work
    # redone" premise the retry is built on).
    assert retry_cmd[2] == runner._JSON_RETRY_PROMPT
    assert retry_cmd[2] != "/code-review --json"

    assert result["retry_attempted"] is True
    assert json.loads(result["result_text"]) == _REVIEW_JSON
    # doc-review finding: the retry's own raw stdout must be persisted
    # alongside the primary dispatch's, not silently discarded — raw/*.txt
    # exists specifically so a parser bug never loses data, and a retried
    # case is exactly the scenario this feature targets.
    assert "Aggregated JSON emitted per contract." in result["raw_stdout"]
    assert "missing assignment" in result["raw_stdout"]


def test_make_isolated_dispatch_fn_retry_also_fails_keeps_original_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the retry ALSO comes back unparseable, the ORIGINAL (still
    unparseable) result_text is preserved for raw-output/debugging
    purposes, and retry_attempted is still True."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    original_text = "Review complete: FAIL overall, no JSON here."
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        text = original_text if len(calls) == 1 else "still just prose"
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=_wrapper_stdout(text)
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 2
    assert result["retry_attempted"] is True
    assert result["result_text"] == original_text


def test_make_isolated_dispatch_fn_no_retry_when_first_call_errored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first dispatch that itself reports is_error: true is not retried —
    resuming a broken run's session isn't expected to help."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=_wrapper_stdout("something went wrong", is_error=True),
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 1
    assert result["retry_attempted"] is False


def test_make_isolated_dispatch_fn_no_retry_when_first_result_already_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first dispatch whose result_text already parses as the --json
    payload triggers no retry at all — the common, non-failure case."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=_wrapper_stdout(json.dumps(_REVIEW_JSON))
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 1
    assert result["retry_attempted"] is False
    assert json.loads(result["result_text"]) == _REVIEW_JSON


def test_make_isolated_dispatch_fn_no_retry_when_first_dispatch_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FIRST dispatch timing out (subprocess.TimeoutExpired) must not
    attempt a retry — there is no completed session to resume. Explicit
    regression coverage for this path (Acceptance Test Critic finding),
    not just the structural guarantee of an early return."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 1
    assert result["retry_attempted"] is False
    assert result["is_error"] is True


def test_make_isolated_dispatch_fn_retry_follow_up_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The RETRY dispatch itself timing out must not crash the case — the
    original (still-unparseable) result_text is preserved and
    retry_attempted stays True (Acceptance + Design critic finding: AC3's
    'times out' sub-mode had no test)."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    original_text = (
        "Per the --json contract, that JSON object is the run's only output."
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=_wrapper_stdout(original_text)
            )
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 2
    assert result["retry_attempted"] is True
    assert result["result_text"] == original_text
    # The retry subprocess itself never produced usable stdout (it raised),
    # but that must still be visible in the persisted raw output rather
    # than silently vanishing — a debugging-time distinction between "the
    # retry ran and also narrated" and "the retry never completed at all."
    assert original_text in result["raw_stdout"]
    assert "retry subprocess failed" in result["raw_stdout"]


def test_make_isolated_dispatch_fn_retry_follow_up_raises_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry dispatch that raises something other than TimeoutExpired
    (e.g. an OSError spawning the subprocess) must not propagate and crash
    the case — same "never let a broken retry sink the case" contract as
    the timeout path, and the same contract cli.py already applies at the
    batch level for `run_case` itself."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    original_text = "Review complete: FAIL overall, no JSON emitted."
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=_wrapper_stdout(original_text)
            )
        raise OSError("could not spawn subprocess")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 2
    assert result["retry_attempted"] is True
    assert result["result_text"] == original_text


def test_make_isolated_dispatch_fn_retry_follow_up_wrapper_is_error_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry whose own wrapper JSON reports is_error: true (the resumed
    session itself errored, distinct from merely being unparseable) must
    not be treated as a successful retry — the ORIGINAL text is kept."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    original_text = (
        "Aggregated JSON emitted to stdout per --json contract; run stops here."
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            stdout = _wrapper_stdout(original_text)
        else:
            stdout = _wrapper_stdout(json.dumps(_REVIEW_JSON), is_error=True)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn()
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 2
    assert result["retry_attempted"] is True
    assert result["result_text"] == original_text


def test_make_isolated_dispatch_fn_retry_on_unparseable_false_suppresses_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`retry_on_unparseable=False` (the `--no-json-retry` path) must
    suppress the retry at the dispatch-closure level, not just at CLI
    argument parsing — proves the flag is actually wired through and
    honored (Acceptance Test Critic finding: AC6 had no end-to-end test)."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=_wrapper_stdout("Aggregated JSON emitted per contract."),
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn(retry_on_unparseable=False)
    result = dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert len(calls) == 1
    assert result["retry_attempted"] is False


def test_make_isolated_dispatch_fn_retry_timeout_override_reaches_subprocess_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`retry_timeout=` must reach the actual retry `subprocess.run` call's
    `timeout=` kwarg — not just be accepted by argparse (Design &
    Architecture Critic finding on the second review pass). The primary
    dispatch keeps the larger `timeout=` budget; only the retry call uses
    the smaller, independently-overridable `retry_timeout`."""
    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _RetryFakeIsolatedDispatch
    )

    seen_timeouts = []

    def fake_run(cmd, **kwargs):
        seen_timeouts.append(kwargs.get("timeout"))
        if len(seen_timeouts) == 1:
            stdout = _wrapper_stdout("Aggregated JSON emitted per contract.")
        else:
            stdout = _wrapper_stdout(json.dumps(_REVIEW_JSON))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn(timeout=1800, retry_timeout=5)
    dispatch_fn("/code-review --json", "/tmp/some-dir")

    assert seen_timeouts == [1800, 5]


def test_run_case_skip_reason_notes_retry_when_retry_attempted(tmp_path: Path) -> None:
    """`run_case`'s skip reason distinguishes a retried-but-still-failed
    dispatch from one where no retry was ever attempted (#999/#1002)."""

    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        return {
            "raw_stdout": json.dumps({"result": "still prose"}),
            "result_text": "still prose",
            "retry_attempted": True,
        }

    record = runner.run_case(
        _CASE,
        checkout_fn=checkout_fn,
        dispatch_fn=dispatch_fn,
        results_dir=tmp_path,
    )
    assert record["skipped"] is True
    assert record["reason"] == "unparseable --json output (after retry)"
def test_override_dev_team_plugin_path_rewrites_install_path(tmp_path: Path) -> None:
    """`_override_dev_team_plugin_path()` (#1010) must rewrite only the
    `dev-team@bfinster` entry's `installPath`, leaving the rest of
    `installed_plugins.json` untouched."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)
    installed_path = plugins_dir / "installed_plugins.json"
    installed_path.write_text(
        json.dumps(
            {
                "plugins": {
                    "dev-team@bfinster": [
                        {
                            "scope": "user",
                            "installPath": "/old/cache/path/10.3.2",
                            "version": "10.3.2",
                        }
                    ],
                    "other-plugin@someone": [{"installPath": "/keep/me"}],
                }
            }
        ),
        encoding="utf-8",
    )

    runner._override_dev_team_plugin_path(tmp_path, "/worktree/plugins/dev-team")

    data = json.loads(installed_path.read_text(encoding="utf-8"))
    assert data["plugins"]["dev-team@bfinster"][0]["installPath"] == (
        "/worktree/plugins/dev-team"
    )
    assert data["plugins"]["other-plugin@someone"][0]["installPath"] == "/keep/me"


def test_override_dev_team_plugin_path_noops_when_file_missing(tmp_path: Path) -> None:
    """Best-effort: no `installed_plugins.json` (e.g. a bare test cell home)
    must not raise."""
    runner._override_dev_team_plugin_path(tmp_path, "/worktree/plugins/dev-team")


def test_make_isolated_dispatch_fn_applies_plugin_path_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When `plugin_path` is passed, `make_isolated_dispatch_fn()`'s dispatch
    closure must apply the override (#1010) after `copy_auth_state()`."""
    home = tmp_path / "cell-home"
    home.mkdir()
    plugins_dir = home / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "dev-team@bfinster": [{"installPath": "/old/cache/path/10.3.2"}]
                }
            }
        ),
        encoding="utf-8",
    )

    class _FakeIsolatedDispatch:
        @staticmethod
        def make_cell_home():
            return home

        @staticmethod
        def copy_auth_state(home):
            return True

        @staticmethod
        def new_session_id():
            return "11111111-1111-1111-1111-111111111111"

        @staticmethod
        def build_env(home):
            return {}

        @staticmethod
        def build_cmd(prompt, session_id, model, cwd=None):
            return ["claude", "-p", prompt]

    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _FakeIsolatedDispatch
    )

    import subprocess as subprocess_module

    installed_path = plugins_dir / "installed_plugins.json"
    seen: Dict[str, Any] = {}

    def fake_run(cmd, **kwargs):
        # home gets rmtree'd in dispatch()'s `finally` right after this
        # call returns, so read the override's effect while it still exists.
        seen["data"] = json.loads(installed_path.read_text(encoding="utf-8"))
        return subprocess_module.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps({"result": "{}"})
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    dispatch_fn = runner.make_isolated_dispatch_fn(
        plugin_path="/worktree/plugins/dev-team"
    )
    dispatch_fn("/code-review --json", str(tmp_path))

    assert seen["data"]["plugins"]["dev-team@bfinster"][0]["installPath"] == (
        "/worktree/plugins/dev-team"
    )


def test_append_and_resume_roundtrip(tmp_path: Path) -> None:
    hit_record = {
        "dataset": "defects4j",
        "project": "Lang",
        "bug_id": "1",
        "skipped": False,
        "hit": True,
    }
    skip_record = {
        "dataset": "bugsjs",
        "project": "Bower",
        "bug_id": "2",
        "skipped": True,
        "reason": "checkout failed",
    }
    runner.append_result(hit_record, tmp_path)
    runner.append_result(skip_record, tmp_path)

    assert (tmp_path / "results.jsonl").is_file()
    assert (tmp_path / "skipped.jsonl").is_file()

    seen = runner.already_processed(tmp_path)
    assert seen == {"defects4j:Lang:1", "bugsjs:Bower:2"}
