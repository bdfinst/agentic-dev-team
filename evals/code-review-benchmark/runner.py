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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import scorer

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)

# `/code-review --json`'s `issues[].severity` enum, mapped onto
# `review-value.jsonl`'s `severity_breakdown` counts (#1256).
_SEVERITY_TO_BREAKDOWN_KEY = {
    "error": "errors",
    "warning": "warnings",
    "suggestion": "suggestions",
}

# Recognized source-file extensions per dataset language (#965). A language
# absent from this mapping is treated as "unknown" — see
# `_touches_recognized_source()` for why that means "don't skip."
_SOURCE_EXTENSIONS: dict[str, tuple] = {
    "java": (".java",),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
}


def _touches_recognized_source(files: list[str], language: str) -> bool:
    """True unless `language` has a recognized-extension mapping and none of
    `files` match it.

    An unmapped `language` returns True (safe default) so a future adapter
    for a language not yet in `_SOURCE_EXTENSIONS` never has all its cases
    silently skipped by this check.
    """
    extensions = _SOURCE_EXTENSIONS.get(language)
    if not extensions:
        return True
    return any(f.endswith(extensions) for f in files)


def _resolve_ground_truth_hunks(
    case: dict[str, Any],
    checkout_dir: str,
    ground_truth_fn: Callable[[str], list[Any]] | None,
) -> list[dict[str, Any]]:
    """The case's own `ground_truth_hunks`, or `ground_truth_fn(checkout_dir)`'s
    when the case doesn't carry them inline (e.g. BugsJS, whose ground truth
    requires the post-checkout git history). Returns `[]` (never `None`) when
    neither source has hunks — same "empty means skip" contract as before."""
    ground_truth_hunks = list(case.get("ground_truth_hunks") or [])
    if not ground_truth_hunks and ground_truth_fn is not None:
        hunks = ground_truth_fn(checkout_dir)
        ground_truth_hunks = [
            h.to_dict() if hasattr(h, "to_dict") else h for h in hunks
        ]
    return ground_truth_hunks


def _extract_review_json(result_text: str | None) -> dict[str, Any] | None:
    """Parse `/code-review --json`'s payload out of a dispatch's final text.

    `/code-review --json` is contractually supposed to print the payload
    and nothing else, but models sometimes narrate first, e.g. "Emitting
    the required aggregated JSON per contract:\n\n```json\n{...}" (#963,
    confirmed live — 40% of an early real sweep was lost to exactly this).
    `_FENCE_RE` therefore searches for a fenced block ANYWHERE in the text
    rather than anchoring to the whole string, and tries the LAST fenced
    block first — if a model emits more than one (an inline example ahead
    of the real payload, say), the final one is the more likely candidate
    — falling back to earlier fences, then to parsing the raw text
    directly if no fence exists at all. Returns `None` on total failure —
    the caller logs a skip, never raises.
    """
    if not result_text:
        return None
    text = result_text.strip()
    fence_matches = list(_FENCE_RE.finditer(text))
    for match in reversed(fence_matches):
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _flatten_findings(review_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the aggregated JSON's `agents[].issues[]` into scorable findings."""
    findings: list[dict[str, Any]] = []
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


def emit_review_value_rows(
    case: dict[str, Any],
    review_json: dict[str, Any],
    results_dir: Any,
    diff_shape: str = "mixed",
) -> None:
    """Append one `review-value.jsonl` row per dispatched lens (#2051).

    Written BY MECHANISM straight from the parsed `/code-review --json`
    payload's `agents[]` list -- which names every agent the panel actually
    dispatched, whether or not it found anything -- rather than by agent
    instruction, the collection bias #2019/#1512 documented in the live
    `/build`/`/code-review` writers of this same file (a round that found
    nothing is markedly less likely to be told to log itself). Every
    dispatched lens gets a row here, including a lens whose `issues` list is
    empty -- the "no-op" case #2019 could not previously observe.

    `source: "harness"` is a value distinct from the live writers'
    `build-checkpoint` / `build-backstop` / `code-review` (see
    `knowledge/telemetry-schema.md`) so harness rows are never silently
    pooled with live ones. Rows land in `results_dir/review-value.jsonl` --
    the harness's own results directory, never `.claude/metrics/` -- which
    is itself a second, structural guarantee against pooling: nothing about
    a harness run writes into the live metrics tree.

    Never called for an unparseable dispatch (`review_json is None`): there
    is no way to attribute a row to a lens without knowing which lenses ran,
    and that failure is already captured by `skipped.jsonl`'s "unparseable
    --json output" reason -- duplicating it here would be a second, weaker
    record of the same fact.
    """
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(results_dir / "review-value.jsonl", "a", encoding="utf-8") as fh:
        for agent in review_json.get("agents", []) or []:
            agent_name = agent.get("agentName")
            if not agent_name:
                continue
            issues = agent.get("issues", []) or []
            breakdown = {"errors": 0, "warnings": 0, "suggestions": 0}
            for issue in issues:
                key = _SEVERITY_TO_BREAKDOWN_KEY.get(issue.get("severity"))
                if key:
                    breakdown[key] += 1
            row = {
                "timestamp": timestamp,
                "source": "harness",
                "dataset": case["dataset"],
                "project": case["project"],
                "bug_id": case["bug_id"],
                "agents_run": [agent_name],
                "issues_found": len(issues),
                "severity_breakdown": breakdown,
                "outcome": "no-op",  # the harness never applies fixes
                "diff_shape": diff_shape,
            }
            fh.write(json.dumps(row) + "\n")


def _build_scoped_dir(checkout_dir: str, files: list[str]) -> str:
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
    case: dict[str, Any],
    reason: str,
    raw_output_path: str | None = None,
    cost_usd: float | None = None,
) -> dict[str, Any]:
    """`cost_usd` is `None` (the default) for every skip reason that fires
    before a dispatch happens (checkout failure, no ground truth, no
    recognized source) — nothing was spent. The one skip reason that fires
    *after* a real dispatch ("unparseable --json output", #1000) passes the
    dispatch's actual `cost_usd` through explicitly, since that case still
    cost real money even though it couldn't be scored."""
    return {
        "dataset": case["dataset"],
        "project": case["project"],
        "bug_id": case["bug_id"],
        "skipped": True,
        "reason": reason,
        "raw_output_path": raw_output_path,
        "cost_usd": cost_usd,
    }


def run_case(
    case: dict[str, Any],
    *,
    checkout_fn: Callable[[str], bool],
    dispatch_fn: Callable[[str, str], dict[str, Any]],
    results_dir: Any,
    ground_truth_fn: Callable[[str], list[Any]] | None = None,
    test_fn: Callable[[str], dict[str, Any]] | None = None,
    scope: str = "fix-only",
    tolerance: int = scorer.DEFAULT_TOLERANCE,
    workdir_root: str | None = None,
    diff_shape: str = "mixed",
) -> dict[str, Any]:
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

    `diff_shape` (#2051) is passed straight through to
    `emit_review_value_rows()` -- Defects4J/BugsJS cases are real production
    bug fixes, never test-only, so callers leave it at the default `"mixed"`;
    the recorded-diff adapter's cases pass their own precomputed shape.
    """
    results_dir = Path(results_dir)
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    checkout_dir = tempfile.mkdtemp(prefix="crb-checkout-", dir=workdir_root)
    review_dir: str | None = None
    try:
        if not checkout_fn(checkout_dir):
            return skip_record(case, "checkout failed")

        ground_truth_hunks = _resolve_ground_truth_hunks(
            case, checkout_dir, ground_truth_fn
        )
        if not ground_truth_hunks:
            return skip_record(case, "no ground-truth hunks")

        ground_truth_files = sorted({h["file"] for h in ground_truth_hunks})

        if not _touches_recognized_source(ground_truth_files, case.get("language", "")):
            return skip_record(case, "ground truth touches no recognized source files")

        test_verification: dict[str, Any] | None = None
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
        cost_usd = dispatch_result.get("cost_usd")

        raw_path = raw_dir / f"{case['dataset']}-{case['project']}-{case['bug_id']}.txt"
        raw_path.write_text(dispatch_result.get("raw_stdout") or "", encoding="utf-8")

        review_json = _extract_review_json(dispatch_result.get("result_text"))
        if review_json is None:
            reason = "unparseable --json output"
            if dispatch_result.get("retry_attempted"):
                reason += " (after retry)"
            return skip_record(case, reason, str(raw_path), cost_usd=cost_usd)

        emit_review_value_rows(case, review_json, results_dir, diff_shape=diff_shape)

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
            "cost_usd": cost_usd,
        }
    finally:
        shutil.rmtree(checkout_dir, ignore_errors=True)
        if review_dir is not None and review_dir != checkout_dir:
            shutil.rmtree(review_dir, ignore_errors=True)


def run_recorded_diff_case(
    case: dict[str, Any],
    *,
    checkout_fn: Callable[[str], bool],
    dispatch_fn: Callable[[str, str], dict[str, Any]],
    results_dir: Any,
    diff_shape: str = "test-only",
    workdir_root: str | None = None,
) -> dict[str, Any]:
    """Run one recorded-diff case (#2051 item 2) end to end.

    Unlike `run_case()`, a recorded-diff case has no ground truth to score
    against — its purpose is purely to give #1964 real `diff_shape:
    "test-only"` `review-value.jsonl` rows, seeded from real `/test-improve`
    Phase-5 diffs. `checkout_fn(workdir) -> bool` materializes the recorded
    diff's file tree into `workdir`; the whole materialized tree is the
    review scope (there is no "ground-truth files" subset to narrow to,
    unlike `run_case()`'s fix-only scoping).

    Returns a lightweight record — never written to `results.jsonl` or
    `skipped.jsonl`. Recall/hit has no meaning for a recorded-diff case;
    mixing a `hit: None` row into those files would corrupt `report.py`'s
    recall math (`_recall()` counts anything but `hit: True` as a miss).
    Append the returned record via `append_recorded_diff_result()` instead.
    """
    results_dir = Path(results_dir)
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    checkout_dir = tempfile.mkdtemp(prefix="crb-recorded-diff-", dir=workdir_root)
    try:
        if not checkout_fn(checkout_dir):
            return {
                "dataset": case["dataset"],
                "project": case["project"],
                "bug_id": case["bug_id"],
                "dispatched": False,
                "reason": "checkout failed",
                "cost_usd": None,
            }

        prompt = f"/code-review --path {checkout_dir} --json"
        dispatch_result = dispatch_fn(prompt, checkout_dir) or {}
        cost_usd = dispatch_result.get("cost_usd")

        raw_path = raw_dir / f"{case['dataset']}-{case['project']}-{case['bug_id']}.txt"
        raw_path.write_text(dispatch_result.get("raw_stdout") or "", encoding="utf-8")

        review_json = _extract_review_json(dispatch_result.get("result_text"))
        if review_json is None:
            reason = "unparseable --json output"
            if dispatch_result.get("retry_attempted"):
                reason += " (after retry)"
            return {
                "dataset": case["dataset"],
                "project": case["project"],
                "bug_id": case["bug_id"],
                "dispatched": True,
                "reason": reason,
                "raw_output_path": str(raw_path),
                "cost_usd": cost_usd,
            }

        emit_review_value_rows(case, review_json, results_dir, diff_shape=diff_shape)

        return {
            "dataset": case["dataset"],
            "project": case["project"],
            "bug_id": case["bug_id"],
            "dispatched": True,
            "reason": None,
            "review_value_rows": len(review_json.get("agents", []) or []),
            "raw_output_path": str(raw_path),
            "cost_usd": cost_usd,
        }
    finally:
        shutil.rmtree(checkout_dir, ignore_errors=True)


def append_recorded_diff_result(record: dict[str, Any], results_dir: Any) -> None:
    """Append `record` to `recorded-diff-log.jsonl`, kept out of
    `results.jsonl`/`skipped.jsonl` deliberately (#2051) — see
    `run_recorded_diff_case()`'s docstring for why."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / "recorded-diff-log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def case_key(record_or_case: dict[str, Any]) -> str:
    return f"{record_or_case['dataset']}:{record_or_case['project']}:{record_or_case['bug_id']}"


def already_processed(results_dir: Any) -> set[str]:
    """Keys already present in results.jsonl or skipped.jsonl — for `--resume`."""
    results_dir = Path(results_dir)
    seen: set[str] = set()
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


def append_result(record: dict[str, Any], results_dir: Any) -> None:
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


def _override_dev_team_plugin_path(home: Path, plugin_path: str) -> None:
    """Rewrite the cell home's copied `installed_plugins.json` so the
    `dev-team@bfinster` entry's `installPath` points at `plugin_path` (#1010).

    Without this, every dispatch loads whatever `copy_auth_state()` carried
    over from the operator's real `~/.claude/plugins/` — the **globally
    cached** plugin install, version-keyed and only refreshed when the
    plugin's `version` string bumps. A live sweep meant to verify a local
    branch's agent/skill change can silently run against a cache that is
    many commits stale, with nothing in the harness surfacing the gap (see
    #1010's repro).

    Best-effort: no-ops if the file is missing, unparseable, or has no
    `dev-team@bfinster` entry (e.g. a bare test cell home) — this override
    is a diagnostic aid for live verification sweeps, not something that
    should ever crash a dispatch.
    """
    installed_path = Path(home) / ".claude" / "plugins" / "installed_plugins.json"
    if not installed_path.is_file():
        return
    try:
        data = json.loads(installed_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    entries = data.get("plugins", {}).get("dev-team@bfinster")
    if not entries:
        return
    for entry in entries:
        entry["installPath"] = str(plugin_path)
    installed_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# #999/#1002: a completed `/code-review --json` dispatch occasionally
# narrates having emitted the JSON instead of actually emitting it, even
# after PR #975 hardened the skill's step-7 wording to specifically forbid
# this — confirmed independently on two more cases post-#975 (58-turn and
# 15-turn runs, so not cleanly explained by turn count/context pressure
# alone). A skill-file wording instruction cannot deterministically force
# what the model's literal final turn contains, so this is a harness-side
# backstop instead of a third wording attempt: one cheap follow-up dispatch
# that RESUMES the same session (`--resume`, not a fresh `--session-id`) and
# asks it to restate the already-computed result as raw JSON only. See
# `plans/issue-999-1002-json-narration.md` for the full investigation.
_JSON_RETRY_PROMPT = (
    "Your previous response completed the /code-review --json review, but "
    "its final text did not contain the required JSON object — a narration "
    "or prose summary was returned instead of the payload. Re-emit the "
    "exact same review result you already computed. Your entire response "
    "must be the raw JSON object itself, per the aggregated JSON schema — "
    "no preamble, no markdown fence, no trailing commentary."
)

# Delimiter joining the primary dispatch's raw stdout to the #999/#1002
# retry's raw stdout in the value `run_case` persists to `raw/*.txt` — so a
# retried case's raw-output file still shows both attempts verbatim (never
# silently discards the retry's own output, matching this file's existing
# "never lose data" contract for raw-output persistence).
_RETRY_RAW_DELIMITER = "\n\n--- #999/#1002 JSON-retry follow-up (--resume) ---\n\n"


def _parse_dispatch_wrapper(raw_stdout: str) -> dict[str, Any]:
    """Parse one dispatch's `--output-format json` wrapper stdout into the
    fields `make_isolated_dispatch_fn`'s closure needs: the model's final
    `result` text, whether the run itself reported an error, and its
    `total_cost_usd` (#1000). Shared by both the primary dispatch and the
    #999/#1002 retry-once follow-up so neither duplicates the other's
    parse/extract logic (Design & Architecture Critic finding during this
    plan's review)."""
    result_text = None
    is_error = True
    cost_usd = None
    try:
        wrapper = json.loads(raw_stdout)
        result_text = wrapper.get("result")
        is_error = bool(wrapper.get("is_error"))
        cost_usd = wrapper.get("total_cost_usd")
    except (json.JSONDecodeError, ValueError):
        pass
    return {"result_text": result_text, "is_error": is_error, "cost_usd": cost_usd}


def make_isolated_dispatch_fn(
    model: str = "sonnet",
    timeout: int = 1800,
    retry_on_unparseable: bool = True,
    retry_timeout: int | None = None,
    plugin_path: str | None = None,
) -> Callable[[str, str], dict[str, Any]]:
    """Build the real, production `dispatch_fn` for `run_case`.

    Reuses `isolated_dispatch`'s scrubbed-env / fresh-session-id isolation
    (the #842 fix) but — unlike `isolated_dispatch.run()` — keeps the
    wrapper JSON's `result` field, which is where `/code-review --json`'s
    actual payload lives as the model's final text. Also carries over the
    operator's real Claude Code login (`copy_auth_state()`, #957) —
    unconditionally, unlike the standalone script's opt-in `--preserve-auth`
    — since running this harness at all presupposes the operator's own
    subscription rather than an `ANTHROPIC_API_KEY`.

    `timeout`'s default was raised 900 -> 1800 after #974 (a 900s single-
    file timeout on `defects4j-Lang-23`/`defects4j-Lang-56` reported against
    #967). Investigated live rather than guessed at: a real, uncontended-
    by-design `/code-review --path <dir> --json` dispatch against a
    deliberately trivial 15-line single-file directory (this module's own
    `isolated_dispatch.py`/`copy_auth_state()` machinery, no artificial
    speedup) still cost 28 turns, 1.28M input tokens, and $1.29 — because
    `skills/code-review/SKILL.md` step 3 dispatches its full ~14-agent
    review roster regardless of file count ("fix-only" scope narrows which
    *files* get reviewed, not how many *agents* run); step 4 hands every
    dispatched agent the complete file content. A real Defects4J case
    (`defects4j-Lang-29`, sampled independently the same session) measured
    even higher: 58 turns, 846s of cumulative nested-call API time (vs.
    368s wall clock — only possible with heavy fan-out), $4.48. Neither run
    hit 900s at the concurrency each happened to run under, but the
    numbers make clear that a larger real ground-truth file (Lang-23's is
    536 lines, Lang-56's 1744) reviewed by the same full roster, especially
    under this harness's `--workers` concurrency multiplying the nested
    `claude -p` dispatch count further, can plausibly exceed the old 900s
    ceiling without any hang — the aggregation step itself
    (`skills/code-review/SKILL.md` step 5) is deterministic parsing with no
    LLM call and no loop, ruled out as a hang source. 1800s is deliberate
    headroom for that now-measured real cost, not an arbitrary bump; see
    `cli.py`'s `--timeout` help text and `plans/issue-974-benchmark-
    timeout-fanout.md` for the full investigation.

    `retry_on_unparseable` (#999/#1002, default `True`): when a completed,
    non-error dispatch's `result` text has no parseable `--json` payload
    (per `_extract_review_json()`), issue exactly ONE follow-up dispatch
    that resumes the SAME session (cheap — no work is redone) asking it to
    re-emit only the JSON. Set `False` to disable this backstop (e.g. for a
    retry-on vs. retry-off recurrence-rate comparison, or a cost-sensitive
    sweep) via `cli.py --no-json-retry`.

    `retry_timeout` (#999/#1002, default `None` -> `min(timeout, 300)`):
    the follow-up retry dispatch's own subprocess timeout, deliberately
    NOT the same (large, 1800s-by-default) budget as the primary dispatch.
    The retry's whole premise is that it's a cheap restatement of an
    already-computed result within the same session, not a fresh review —
    reusing the full primary timeout would let a stuck/looping retry cost
    nearly as much wall-clock as the original dispatch, undermining that
    premise (Design & Architecture Critic finding during this plan's
    review). 300s is a reasonable, deliberately conservative ceiling for
    that — not an empirically measured number (no live retry-cost data
    exists yet); override via `cli.py --json-retry-timeout` if a live
    sweep later shows it's too tight or too loose.

    `plugin_path` (#1010): when set, overrides the `dev-team@bfinster` entry
    in the cell home's copied `installed_plugins.json` to point at this
    path instead of the globally cached install `copy_auth_state()` carried
    over — see `_override_dev_team_plugin_path()`. Use this to verify a
    local branch's agent/skill change actually reaches the dispatch, rather
    than silently testing stale cached plugin content.
    """
    isolated_dispatch = _load_isolated_dispatch()
    effective_retry_timeout = (
        retry_timeout if retry_timeout is not None else min(timeout, 300)
    )

    def dispatch(prompt: str, cwd: str) -> dict[str, Any]:
        home = isolated_dispatch.make_cell_home()
        isolated_dispatch.copy_auth_state(home)
        if plugin_path:
            _override_dev_team_plugin_path(home, plugin_path)
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
            shutil.rmtree(str(home), ignore_errors=True)
            return {
                "raw_stdout": "",
                "result_text": None,
                "is_error": True,
                "retry_attempted": False,
            }

        raw_stdout = proc.stdout or ""
        parsed = _parse_dispatch_wrapper(raw_stdout)
        result_text = parsed["result_text"]
        cost_usd = parsed["cost_usd"]
        retry_attempted = False

        if (
            retry_on_unparseable
            and not parsed["is_error"]
            and _extract_review_json(result_text) is None
        ):
            retry_attempted = True
            retry_cmd = isolated_dispatch.build_cmd(
                _JSON_RETRY_PROMPT, session_id, model, cwd=cwd, resume=True
            )
            try:
                retry_proc = subprocess.run(
                    retry_cmd,
                    cwd=cwd,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=effective_retry_timeout,
                )
            except subprocess.TimeoutExpired:
                retry_proc = None
            except Exception:  # noqa: BLE001 - a broken retry must not crash the case
                retry_proc = None

            if retry_proc is not None:
                retry_raw_stdout = retry_proc.stdout or ""
                retry_parsed = _parse_dispatch_wrapper(retry_raw_stdout)
                if (
                    not retry_parsed["is_error"]
                    and _extract_review_json(retry_parsed["result_text"]) is not None
                ):
                    result_text = retry_parsed["result_text"]
                    # #1000's cost tracking must reflect the real total
                    # spend for this case, including the retry's own cost —
                    # not just the primary dispatch's.
                    if retry_parsed["cost_usd"] is not None:
                        cost_usd = (cost_usd or 0) + retry_parsed["cost_usd"]
            else:
                retry_raw_stdout = "<retry subprocess failed: timeout or exception, no stdout captured>"
            # #999/#1002 doc-review finding: the retry's own raw stdout must
            # not be silently discarded — raw_dir/*.txt's whole purpose (see
            # `run_case`) is "never lose data even on a parser bug," and a
            # retried case is exactly the scenario this feature targets.
            raw_stdout = raw_stdout + _RETRY_RAW_DELIMITER + retry_raw_stdout

        shutil.rmtree(str(home), ignore_errors=True)
        return {
            "raw_stdout": raw_stdout,
            "result_text": result_text,
            "retry_attempted": retry_attempted,
            "cost_usd": cost_usd,
        }

    return dispatch


if __name__ == "__main__":
    sys.stderr.write("runner.py is a library — invoke via cli.py\n")
    raise SystemExit(1)
