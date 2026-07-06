"""Runner for the /code-review benchmark harness (#821).

Per case: checkout the buggy revision -> scope the review to just the
ground-truth files (cost control, default) or the full repo (--full-repo)
-> dispatch `/code-review --path <dir> --json` headlessly -> save raw output
verbatim -> parse findings -> score against ground truth -> append one
record to results.jsonl (or skipped.jsonl on any failure).

`dispatch_fn` and `checkout_fn` are always injected by the caller (cli.py
binds them to a specific adapter + config) — this module never imports an
adapter or shells out to `claude` itself, so it can be unit-tested with
plain callables and no external tools. See `make_isolated_dispatch_fn()` for
the real, production dispatch implementation, built on the existing
`isolated_dispatch.py` (the #842 fix) but kept separate because that module
normalizes away the exact field (`result`) this harness needs.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import scorer

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def _extract_review_json(result_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse `/code-review --json`'s payload out of a dispatch's final text.

    Handles the payload being wrapped in a markdown code fence (models
    sometimes do this even when told to emit JSON only) before parsing.
    Returns None on any failure — the caller logs a skip, never raises.
    """
    if not result_text:
        return None
    text = result_text.strip()
    fence_match = _FENCE_RE.match(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _flatten_findings(review_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten the aggregated JSON's `agents[].issues[]` into scorable findings."""
    findings: List[Dict[str, Any]] = []
    for agent in review_json.get("agents", []) or []:
        agent_name = agent.get("agentName")
        for issue in agent.get("issues", []) or []:
            findings.append(
                {
                    "file": issue.get("file"),
                    "line": issue.get("line"),
                    "severity": issue.get("severity"),
                    "confidence": issue.get("confidence"),
                    "message": issue.get("message"),
                    "agentName": agent_name,
                }
            )
    return findings


def _build_scoped_dir(checkout_dir: str, files: List[str]) -> str:
    """Copy only `files` (relative paths) out of `checkout_dir`, preserving structure."""
    scoped = tempfile.mkdtemp(prefix="crb-scope-")
    for rel_path in files:
        src = Path(checkout_dir) / rel_path
        if not src.is_file():
            continue
        dst = Path(scoped) / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return scoped


def skip_record(
    case: Dict[str, Any], reason: str, raw_output_path: Optional[str] = None
) -> Dict[str, Any]:
    return {
        "dataset": case["dataset"],
        "project": case["project"],
        "bug_id": case["bug_id"],
        "skipped": True,
        "reason": reason,
        "raw_output_path": raw_output_path,
    }


def run_case(
    case: Dict[str, Any],
    *,
    checkout_fn: Callable[[str], bool],
    dispatch_fn: Callable[[str, str], Dict[str, Any]],
    results_dir: Any,
    ground_truth_fn: Optional[Callable[[str], List[Any]]] = None,
    test_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    scope: str = "fix-only",
    tolerance: int = scorer.DEFAULT_TOLERANCE,
    workdir_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one BenchmarkCase (as a dict, matching `BenchmarkCase.to_dict()`) end to end.

    `checkout_fn(workdir) -> bool` and `ground_truth_fn(workdir) -> [hunk]`
    (used only when `case["ground_truth_hunks"]` is empty, e.g. BugsJS, whose
    ground truth requires the post-checkout git history) are pre-bound
    closures the caller builds per case — this function has no knowledge of
    which dataset/adapter it's running. `test_fn(checkout_dir) -> dict`,
    when supplied, is called against the full checkout (before any
    `fix-only` scoping copies files out) as a diagnostic sanity check that
    the buggy revision reproduces a failing test; it never gates or skips
    the case, and its result lands in the record as `test_verification`.
    """
    results_dir = Path(results_dir)
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    checkout_dir = tempfile.mkdtemp(prefix="crb-checkout-", dir=workdir_root)
    review_dir: Optional[str] = None
    try:
        if not checkout_fn(checkout_dir):
            return skip_record(case, "checkout failed")

        ground_truth_hunks = list(case.get("ground_truth_hunks") or [])
        if not ground_truth_hunks and ground_truth_fn is not None:
            hunks = ground_truth_fn(checkout_dir)
            ground_truth_hunks = [
                h.to_dict() if hasattr(h, "to_dict") else h for h in hunks
            ]
        if not ground_truth_hunks:
            return skip_record(case, "no ground-truth hunks")

        ground_truth_files = sorted({h["file"] for h in ground_truth_hunks})

        test_verification: Optional[Dict[str, Any]] = None
        if test_fn is not None:
            try:
                test_verification = test_fn(checkout_dir)
            except Exception as exc:  # noqa: BLE001 - a broken test_fn must not crash the case
                test_verification = {
                    "configured": False,
                    "ran": False,
                    "reproduced": False,
                    "error": str(exc),
                }

        if scope == "full-repo":
            review_dir = checkout_dir
        else:
            review_dir = _build_scoped_dir(checkout_dir, ground_truth_files)

        prompt = f"/code-review --path {review_dir} --json"
        dispatch_result = dispatch_fn(prompt, review_dir) or {}

        raw_path = raw_dir / f"{case['dataset']}-{case['project']}-{case['bug_id']}.txt"
        raw_path.write_text(dispatch_result.get("raw_stdout") or "", encoding="utf-8")

        review_json = _extract_review_json(dispatch_result.get("result_text"))
        if review_json is None:
            return skip_record(case, "unparseable --json output", str(raw_path))

        findings = _flatten_findings(review_json)
        scored = scorer.score(ground_truth_hunks, findings, tolerance=tolerance)

        return {
            "dataset": case["dataset"],
            "project": case["project"],
            "bug_id": case["bug_id"],
            "skipped": False,
            "hit": scored["hit"],
            "ground_truth_hunks": ground_truth_hunks,
            "findings": findings,
            "unmatched_findings": scored["unmatched"],
            "raw_output_path": str(raw_path),
            "test_verification": test_verification,
        }
    finally:
        shutil.rmtree(checkout_dir, ignore_errors=True)
        if review_dir is not None and review_dir != checkout_dir:
            shutil.rmtree(review_dir, ignore_errors=True)


def case_key(record_or_case: Dict[str, Any]) -> str:
    return f"{record_or_case['dataset']}:{record_or_case['project']}:{record_or_case['bug_id']}"


def already_processed(results_dir: Any) -> Set[str]:
    """Keys already present in results.jsonl or skipped.jsonl — for `--resume`."""
    results_dir = Path(results_dir)
    seen: Set[str] = set()
    for name in ("results.jsonl", "skipped.jsonl"):
        path = results_dir / name
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                seen.add(case_key(record))
    return seen


def append_result(record: Dict[str, Any], results_dir: Any) -> None:
    """Append `record` to results.jsonl or skipped.jsonl, per its `skipped` flag."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    name = "skipped.jsonl" if record.get("skipped") else "results.jsonl"
    with open(results_dir / name, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _load_isolated_dispatch():
    """Import the #842 fix's isolated-dispatch module by file path.

    Not a normal importable package (it lives under a plugin skill's
    `scripts/` dir), so this resolves the path relative to the repo root
    rather than assuming it's on `sys.path`.
    """
    repo_root = Path(__file__).resolve().parents[2]
    module_path = (
        repo_root
        / "plugins"
        / "dev-team"
        / "skills"
        / "headless-run"
        / "scripts"
        / "isolated_dispatch.py"
    )
    spec = importlib.util.spec_from_file_location("isolated_dispatch", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load isolated_dispatch from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_isolated_dispatch_fn(
    model: str = "sonnet", timeout: int = 900
) -> Callable[[str, str], Dict[str, Any]]:
    """Build the real, production `dispatch_fn` for `run_case`.

    Reuses `isolated_dispatch`'s scrubbed-env / fresh-session-id isolation
    (the #842 fix) but — unlike `isolated_dispatch.run()` — keeps the
    wrapper JSON's `result` field, which is where `/code-review --json`'s
    actual payload lives as the model's final text. Also carries over the
    operator's real Claude Code login (`copy_auth_state()`, #957) —
    unconditionally, unlike the standalone script's opt-in `--preserve-auth`
    — since running this harness at all presupposes the operator's own
    subscription rather than an `ANTHROPIC_API_KEY`.
    """
    isolated_dispatch = _load_isolated_dispatch()

    def dispatch(prompt: str, cwd: str) -> Dict[str, Any]:
        home = isolated_dispatch.make_cell_home()
        isolated_dispatch.copy_auth_state(home)
        session_id = isolated_dispatch.new_session_id()
        env = isolated_dispatch.build_env(home)
        cmd = isolated_dispatch.build_cmd(prompt, session_id, model, cwd=cwd)
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"raw_stdout": "", "result_text": None, "is_error": True}
        finally:
            shutil.rmtree(str(home), ignore_errors=True)

        raw_stdout = proc.stdout or ""
        result_text = None
        try:
            wrapper = json.loads(raw_stdout)
            result_text = wrapper.get("result")
        except (json.JSONDecodeError, ValueError):
            pass
        return {"raw_stdout": raw_stdout, "result_text": result_text}

    return dispatch


if __name__ == "__main__":
    sys.stderr.write("runner.py is a library — invoke via cli.py\n")
    raise SystemExit(1)
