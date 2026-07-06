"""Unit tests for the #821 benchmark harness's runner.

All dispatch/checkout behavior is injected (no real subprocess, no real
`claude` invocation, no network) — mirrors the dependency-injection style
`scripts/agent_calibrate.py` uses for its `dispatch_fn`, rather than patching
`subprocess.run` directly.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

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


def _dispatch_result(review_json: Dict[str, Any] = _REVIEW_JSON) -> Dict[str, Any]:
    """A dispatch_fn return value shaped like the real `make_isolated_dispatch_fn`
    output: both the raw wrapper stdout AND the already-extracted `result_text`
    (the runner reads `result_text` directly; it does not re-parse `raw_stdout`)."""
    result_text = json.dumps(review_json)
    return {
        "raw_stdout": json.dumps({"result": result_text}),
        "result_text": result_text,
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


def test_run_case_checkout_failure_is_skipped(tmp_path: Path) -> None:
    record = runner.run_case(
        _CASE,
        checkout_fn=lambda workdir: False,
        dispatch_fn=lambda prompt, cwd: {},
        results_dir=tmp_path,
    )
    assert record["skipped"] is True
    assert record["reason"] == "checkout failed"


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


def test_run_case_unparseable_json_is_skipped(tmp_path: Path) -> None:
    def checkout_fn(workdir: str) -> bool:
        _seed_checkout(workdir, ["src/Foo.java"])
        return True

    def dispatch_fn(prompt: str, cwd: str) -> Dict[str, Any]:
        return {
            "raw_stdout": json.dumps({"result": "not json at all"}),
            "result_text": "not json at all",
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


def test_make_isolated_dispatch_fn_carries_over_auth_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`make_isolated_dispatch_fn()`'s dispatch closure must call
    `copy_auth_state()` (#957) so the harness's own runs keep the
    operator's real Claude Code login — unlike the standalone
    `isolated_dispatch.py` script/skill, where this is opt-in."""
    calls = []

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

    monkeypatch.setattr(
        runner, "_load_isolated_dispatch", lambda: _FakeIsolatedDispatch
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
