#!/usr/bin/env python3
"""Band calibration — slice 3 of epic #879 (issue #882).

`/agent-eval --calibrate [--agent <name>]` validates that a review agent's
(or advisory skill's) *declared* effort band (`effort: low|medium|high` in
its frontmatter) is actually the cheapest band whose eval fixtures clear the
target's floor in `knowledge/calibration-floors.json` (#880). It walks the
three canonical bands cheapest-first (low, medium, high), resolving each to
a concrete model via `hooks/lib/model_resolve.py` (honoring
`.claude/model-ladder.json` when present), and stops at the first band whose
fixture pass rate — quarantined fixtures excluded — clears the floor.

This module is the testable core. The "dispatch fixtures at a given model
and see if they pass" step is never hard-wired to a real subprocess here —
it is always an injected callable (`pass_rate_fn` / `dispatch_fn`), so unit
tests can stub it without spawning a `claude -p` process or spending any
tokens. Only `main()` (the real CLI entrypoint) wires in a genuine
dispatcher, and that path is deliberately untested (it is a thin adapter
over `claude -p ... --output-format json` + `eval_grade.run_grading`).

Verdicts
--------
- ``aligned``             — the first band clearing the floor is the declared
  band. No diff.
- ``downgrade-available`` — a band CHEAPER than declared clears the floor.
  Report carries a ready-to-apply ``effort:`` frontmatter diff.
- ``upgrade-required``    — the declared band's own pass rate does NOT clear
  the floor, but some MORE EXPENSIVE band does. Report carries a diff
  recommending the more expensive band.
- ``floor-failure``       — no band (low/medium/high) clears the floor. No
  recommendation.
- ``uncalibratable``      — the target has zero eval fixtures (or no
  calibration-floors.json entry, which can't happen for a fixture-bearing
  target once `check_calibration_floors_sync.py` is green, but is handled
  the same way defensively). Recorded with a fixture-gap count.

This module NEVER edits any file under `plugins/dev-team/agents/` or
`plugins/dev-team/skills/` — report-only, always. The ready-to-apply diff in
the report is for a human (or a future slice) to apply by hand.

Quarantine
----------
Flaky pairs are already tracked by `scripts/eval_variance.py`
(`write_quarantine`), persisted as ``{"schema": "eval-variance/v1",
"quarantine": ["<stem>::<target>", ...], ...}`` at `memory/eval-variance.json`
by default (see agent-eval SKILL.md Step 5). This script reuses that exact
shape/location rather than inventing a new one: `--quarantine <path>`
defaults to `<repo-root>/memory/eval-variance.json`; a missing file means no
pairs are quarantined (never an error). A pair named there is excluded from
every band's pass-rate denominator and named in the report.

Calibration record
-------------------
For every target calibrated, a record is written/overwritten (one entry per
target, keyed by target name) at ``<repo-root>/.claude/evals/
calibration-records.json``:

    {
      "<target>": {
        "target": "<target>",
        "timestamp": "...Z",
        "declared_band": "medium",
        "calibrated_band": "low",
        "verdict": "downgrade-available",
        "routing_hash": "<sha256 over model-routing.json + model-ladder.json>"
      },
      ...
    }

This is consumed by a *future* slice (#883, staleness detection against the
routing/ladder hash) — this slice only writes it, never reads it back for
gating.

Report
------
Written to ``<repo-root>/.claude/evals/reports/<timestamp>-calibration.md``:
per-target band pass-rate table, declared vs. calibrated band, verdict, the
apply-ready diff (downgrade-available / upgrade-required only), any
quarantined fixtures excluded, and any uncalibratable targets with their
fixture-gap count.

Cost preflight
--------------
Before any dispatch, the worst-case dispatch count — ``len(fixtures) * 3``
(3 bands; a run that stops early spends less, this is the ceiling) minus
cache hits (via `scripts/eval_cache.py`'s fingerprint cache, queried per
band-model) — is printed. `--in-session` is refused outright: calibration
must dispatch through fresh subprocesses so it grades what's on disk, not a
stale in-session load (mirrors agent-eval's own Dispatch mode contract).

Stdlib-only. Python 3.8+. See docs/adr/0014-python-for-cross-os-scripts.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_cache import (  # noqa: E402
    Dirs,
    cache_get,
    compute_fingerprint,
    corpus_pairs,
    load_cache,
)
from eval_grade import run_grading  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "dev-team" / "hooks" / "lib"))
try:
    from model_resolve import resolve_band  # noqa: E402
except ImportError:  # pragma: no cover - exercised only if the repo layout moves
    def resolve_band(band: str, routing_path=None, ladder_path=None) -> str:
        raise RuntimeError("hooks/lib/model_resolve.py not importable")


BANDS: Tuple[str, str, str] = ("low", "medium", "high")
BAND_INDEX: Dict[str, int] = {b: i for i, b in enumerate(BANDS)}

_EFFORT_RE = re.compile(r"^effort:\s*['\"]?([A-Za-z]+)['\"]?\s*$")
DEFAULT_DECLARED_BAND = "medium"  # used when a target declares no effort band

# `claude -p ... --output-format json` wraps the agent's answer in a CLI result
# envelope; the structured review is fenced JSON inside the `result` text. This
# mirrors evals/code-review-benchmark/runner.py's `_extract_review_json` /
# `_FENCE_RE` (kept as a local copy to avoid a cross-tree import into the
# benchmark harness, whose tests bind to `runner._extract_review_json`).
_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _extract_review_json(result_text):
    """Parse a review agent's fenced JSON payload out of dispatch text.

    Models sometimes narrate before the payload, or emit an inline example
    fence ahead of the real one, so search for a fence ANYWHERE and try the
    LAST one first, then earlier fences, then the raw text. Returns ``None``
    on total failure — the caller treats that as a non-passing dispatch.
    """
    if not result_text:
        return None
    text = result_text.strip()
    for match in reversed(list(_FENCE_RE.finditer(text))):
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Declared band lookup.
# ---------------------------------------------------------------------------

def read_declared_band(target: str, dirs: Dirs) -> str:
    """Read `effort:` from an agent's or skill's frontmatter.

    Checks `agents/<target>.md` first, then `skills/<target>/SKILL.md`.
    Falls back to DEFAULT_DECLARED_BAND ("medium") when neither file exists,
    the file has no `effort:` key (some advisory skills, e.g.
    test-design-advisor, declare none), or the value isn't a recognized band.
    """
    for candidate in (dirs.agents / f"{target}.md", dirs.skills / target / "SKILL.md"):
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            m = _EFFORT_RE.match(line.strip())
            if m:
                band = m.group(1).lower()
                if band in BAND_INDEX:
                    return band
        break  # file exists but no effort key — stop, don't fall through to skill
    return DEFAULT_DECLARED_BAND


# ---------------------------------------------------------------------------
# Floors.
# ---------------------------------------------------------------------------

def load_floors(floors_path: Path) -> dict:
    try:
        data = json.loads(floors_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Quarantine (reuses eval_variance.py's write_quarantine shape).
# ---------------------------------------------------------------------------

def load_quarantine(path: Path) -> Set[str]:
    """Return the set of quarantined `<stem>::<target>` pair names.

    Reads the `eval-variance/v1` shape written by
    `scripts/eval_variance.py`'s `write_quarantine` (`{"quarantine": [...]}`
    at `memory/eval-variance.json` by default). A missing or unreadable file
    means no pairs are quarantined — never an error.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    q = data.get("quarantine", [])
    if not isinstance(q, list):
        return set()
    return {p for p in q if isinstance(p, str)}


# ---------------------------------------------------------------------------
# Targets to calibrate.
# ---------------------------------------------------------------------------

def target_universe(dirs: Dirs) -> List[str]:
    """Every agent/skill name on disk — the full set `--calibrate` (no
    `--agent`) sweeps, so a fixture-less target still surfaces as
    uncalibratable rather than silently being skipped."""
    names: Set[str] = set()
    if dirs.agents.is_dir():
        names.update(p.stem for p in dirs.agents.glob("*.md"))
    if dirs.skills.is_dir():
        names.update(p.parent.name for p in dirs.skills.glob("*/SKILL.md"))
    return sorted(names)


def fixtures_for_target(target: str, dirs: Dirs) -> List[str]:
    """`<stem>::<target>` pair names applicable to this target."""
    return sorted(pair for pair, _block in corpus_pairs(dirs, only={target}))


# ---------------------------------------------------------------------------
# Pass-rate computation — injectable dispatch.
# ---------------------------------------------------------------------------

DispatchFn = Callable[[str, str], bool]  # (pair, model) -> passed
PassRateFn = Callable[[str, str, str, List[str], Set[str]],
                      Tuple[float, int, int, List[str]]]


def make_pass_rate_fn(dispatch_fn: DispatchFn) -> PassRateFn:
    """Wrap a per-pair `dispatch_fn(pair, model) -> bool` into a
    `pass_rate_fn(target, band, model, pairs, quarantined) ->
    (rate, total, passed, excluded_names)` that excludes quarantined pairs
    from the denominator, per Gherkin scenario 6."""

    def pass_rate_fn(target: str, band: str, model: str, pairs: List[str],
                      quarantined: Set[str]) -> Tuple[float, int, int, List[str]]:
        excluded = sorted(p for p in pairs if p in quarantined)
        active = [p for p in pairs if p not in quarantined]
        if not active:
            # Every fixture for this target is quarantined: nothing to grade.
            return 1.0, 0, 0, excluded
        passed = sum(1 for p in active if dispatch_fn(p, model))
        return passed / len(active), len(active), passed, excluded

    return pass_rate_fn


# ---------------------------------------------------------------------------
# Calibration.
# ---------------------------------------------------------------------------

def calibrate_target(
    target: str,
    dirs: Dirs,
    floors: dict,
    quarantined: Set[str],
    pass_rate_fn: PassRateFn,
    routing_path: Optional[Path] = None,
    ladder_path: Optional[Path] = None,
) -> dict:
    """Compute the calibration outcome for one target.

    Returns a dict with keys: target, verdict, declared_band,
    calibrated_band (None for floor-failure/uncalibratable), floor,
    band_results ({band: {rate, total, passed, model}}), quarantined
    (excluded pair names, deduped across bands), fixture_gap (only set for
    uncalibratable).
    """
    pairs = fixtures_for_target(target, dirs)
    if not pairs:
        return {
            "target": target,
            "verdict": "uncalibratable",
            "declared_band": read_declared_band(target, dirs),
            "calibrated_band": None,
            "floor": None,
            "band_results": {},
            "quarantined": [],
            "fixture_gap": 0,
        }

    floor_entry = floors.get(target)
    if not floor_entry or not isinstance(floor_entry, dict):
        # A fixture-bearing target with no floor entry — check_calibration_
        # floors_sync.py guards against this on `main`, but degrade safely
        # rather than crash if it happens transiently.
        return {
            "target": target,
            "verdict": "uncalibratable",
            "declared_band": read_declared_band(target, dirs),
            "calibrated_band": None,
            "floor": None,
            "band_results": {},
            "quarantined": [],
            "fixture_gap": 0,
        }

    floor = floor_entry.get("floor")
    declared_band = read_declared_band(target, dirs)

    band_results: Dict[str, dict] = {}
    calibrated_band: Optional[str] = None
    all_excluded: Set[str] = set()

    for band in BANDS:
        model = resolve_band(band, routing_path=routing_path, ladder_path=ladder_path)
        rate, total, passed, excluded = pass_rate_fn(target, band, model, pairs, quarantined)
        all_excluded.update(excluded)
        band_results[band] = {
            "rate": rate,
            "total": total,
            "passed": passed,
            "model": model,
        }
        if calibrated_band is None and rate >= floor:
            calibrated_band = band

    if calibrated_band is None:
        verdict = "floor-failure"
    elif calibrated_band == declared_band:
        verdict = "aligned"
    elif BAND_INDEX[calibrated_band] < BAND_INDEX.get(declared_band, BAND_INDEX[DEFAULT_DECLARED_BAND]):
        verdict = "downgrade-available"
    else:
        verdict = "upgrade-required"

    return {
        "target": target,
        "verdict": verdict,
        "declared_band": declared_band,
        "calibrated_band": calibrated_band,
        "floor": floor,
        "band_results": band_results,
        "quarantined": sorted(all_excluded),
        "fixture_gap": None,
    }


# ---------------------------------------------------------------------------
# Cost preflight.
# ---------------------------------------------------------------------------

def worst_case_dispatch_count(num_fixtures: int, num_bands: int = len(BANDS)) -> int:
    """Worst case: every band gets dispatched for every fixture (no early
    stop). This is the ceiling printed before any real dispatch."""
    return num_fixtures * num_bands


def cache_hit_count(
    pairs: List[str],
    dirs: Dirs,
    cache_path: Path,
    routing_path: Optional[Path],
    ladder_path: Optional[Path],
) -> int:
    """How many (pair, band-model) fingerprints already have a memoized PASS
    in `scripts/eval_cache.py`'s replay cache — these need no dispatch."""
    cache = load_cache(cache_path)
    hits = 0
    for band in BANDS:
        model = resolve_band(band, routing_path=routing_path, ladder_path=ladder_path)
        for pair in pairs:
            sha, _ = compute_fingerprint(pair, dirs, model)
            if cache_get(cache, pair, sha) is not None:
                hits += 1
    return hits


def cost_preflight(
    pairs: List[str],
    dirs: Dirs,
    cache_path: Path,
    routing_path: Optional[Path],
    ladder_path: Optional[Path],
) -> Tuple[int, int, int]:
    """Return (worst_case, cache_hits, net_dispatch_count)."""
    worst_case = worst_case_dispatch_count(len(pairs))
    hits = cache_hit_count(pairs, dirs, cache_path, routing_path, ladder_path)
    return worst_case, hits, max(worst_case - hits, 0)


# ---------------------------------------------------------------------------
# Routing/ladder content hash — folded into each target's calibration record
# so a future staleness check (#883) can detect drift.
# ---------------------------------------------------------------------------

def routing_hash(routing_path: Path, ladder_path: Optional[Path]) -> str:
    h = hashlib.sha256()
    for p in (routing_path, ladder_path):
        if p is not None and p.exists():
            try:
                h.update(p.read_bytes())
            except OSError:
                pass
        h.update(b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Calibration record persistence.
# ---------------------------------------------------------------------------

def load_records(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_records(path: Path, records: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")


def build_record(result: dict, rhash: str, now: Optional[str] = None) -> dict:
    return {
        "target": result["target"],
        "timestamp": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "declared_band": result["declared_band"],
        "calibrated_band": result["calibrated_band"],
        "verdict": result["verdict"],
        "routing_hash": rhash,
    }


# ---------------------------------------------------------------------------
# Report generation.
# ---------------------------------------------------------------------------

def effort_diff_block(declared_band: str, calibrated_band: str) -> str:
    return (
        "```diff\n"
        f"- effort: {declared_band}\n"
        f"+ effort: {calibrated_band}\n"
        "```\n"
    )


def render_report(results: List[dict], timestamp: str, preflight: Optional[Tuple[int, int, int]] = None) -> str:
    lines = [f"# Band Calibration Report — {timestamp}", ""]
    if preflight:
        worst_case, hits, net = preflight
        lines.append("## Cost preflight")
        lines.append("")
        lines.append(f"Worst-case dispatch count: {worst_case} "
                      f"(fixtures x 3 bands) - {hits} cache hit(s) = {net} dispatch(es).")
        lines.append("")

    calibratable = [r for r in results if r["verdict"] != "uncalibratable"]
    uncalibratable = [r for r in results if r["verdict"] == "uncalibratable"]

    lines.append("## Targets")
    lines.append("")
    for r in calibratable:
        lines.append(f"### {r['target']}")
        lines.append("")
        lines.append(f"- Declared band: `{r['declared_band']}`")
        lines.append(f"- Calibrated band: `{r['calibrated_band']}`")
        lines.append(f"- Verdict: **{r['verdict']}**")
        lines.append(f"- Floor: {r['floor']}")
        lines.append("")
        lines.append("| Band | Model | Pass rate | Passed/Total |")
        lines.append("| --- | --- | --- | --- |")
        for band in BANDS:
            br = r["band_results"].get(band)
            if not br:
                continue
            lines.append(
                f"| {band} | {br['model']} | {br['rate']:.0%} | "
                f"{br['passed']}/{br['total']} |"
            )
        lines.append("")
        if r["quarantined"]:
            lines.append(
                "Quarantined fixtures excluded from pass rate: "
                + ", ".join(f"`{q}`" for q in r["quarantined"])
            )
            lines.append("")
        if r["verdict"] in ("downgrade-available", "upgrade-required"):
            lines.append("Apply-ready diff:")
            lines.append("")
            lines.append(effort_diff_block(r["declared_band"], r["calibrated_band"]))

    if uncalibratable:
        lines.append("## Uncalibratable")
        lines.append("")
        for r in uncalibratable:
            lines.append(f"- `{r['target']}` — fixture-gap count: {r['fixture_gap']}")
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Real dispatcher (untested path) — the only place that shells out to a real
# model. Grades a single pair by dispatching `claude -p` and running it
# through eval_grade.run_grading for that one target.
# ---------------------------------------------------------------------------

def real_dispatch_fn(pair: str, model: str, dirs: Dirs) -> bool:  # pragma: no cover
    stem, _, target = pair.partition("::")
    from eval_cache import resolve_fixture_files  # local import, avoids cycle at module load
    spec_path = dirs.expected / f"{stem}.json"
    spec = json.loads(spec_path.read_text())
    fixture_files = resolve_fixture_files(stem, spec, dirs)
    if not fixture_files:
        return False
    fixture_path = fixture_files[0] if len(fixture_files) == 1 else fixture_files[0].parent
    cmd = [
        "claude", "-p", f"/review-agent {target} {fixture_path}",
        "--output-format", "json", "--model", model,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    # The `--output-format json` envelope carries the agent's answer as free
    # text in `result`; the structured review is a fenced JSON block inside it.
    # Extract that block (falling back to the raw stdout if the shape differs).
    result_text = envelope.get("result") if isinstance(envelope, dict) else None
    actual = _extract_review_json(result_text if result_text is not None else proc.stdout)
    if actual is None:
        return False
    actuals = {stem: {"agents": {target: actual}}}
    results, _ = run_grading(dirs.expected, actuals, None, only={target})
    return any(p == pair and ok for p, ok, _ in results)


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--expected-dir")
    ap.add_argument("--fixtures-dir")
    ap.add_argument("--plugin-root")
    ap.add_argument("--agent", help="calibrate only this target (agent or skill name)")
    ap.add_argument("--in-session", action="store_true",
                     help="refused — calibration requires fresh-subprocess dispatch")
    ap.add_argument("--quarantine", help="quarantine source (default: "
                     "<repo-root>/memory/eval-variance.json)")
    ap.add_argument("--floors", help="calibration-floors.json path")
    ap.add_argument("--cache", help="eval fingerprint cache (default: "
                     "<repo-root>/evals/.eval-cache.json)")
    ap.add_argument("--model-routing", help="knowledge/model-routing.json path")
    ap.add_argument("--model-ladder", help=".claude/model-ladder.json path")
    ap.add_argument("--reports-dir", help="default: <repo-root>/.claude/evals/reports")
    ap.add_argument("--records", help="default: <repo-root>/.claude/evals/calibration-records.json")
    args = ap.parse_args(argv)

    if args.in_session:
        print(
            "error: calibration requires fresh-subprocess dispatch (--calibrate "
            "cannot be combined with --in-session — it must grade what is "
            "currently on disk, not a stale in-session load).",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(args.repo_root).resolve()
    dirs = Dirs(
        repo_root,
        Path(args.expected_dir).resolve() if args.expected_dir else None,
        Path(args.fixtures_dir).resolve() if args.fixtures_dir else None,
        Path(args.plugin_root).resolve() if args.plugin_root else None,
    )
    quarantine_path = Path(args.quarantine) if args.quarantine else repo_root / "memory" / "eval-variance.json"
    floors_path = Path(args.floors) if args.floors else dirs.knowledge / "calibration-floors.json"
    cache_path = Path(args.cache) if args.cache else repo_root / "evals" / ".eval-cache.json"
    routing_path = Path(args.model_routing) if args.model_routing else dirs.knowledge / "model-routing.json"
    ladder_path = Path(args.model_ladder) if args.model_ladder else repo_root / ".claude" / "model-ladder.json"
    reports_dir = Path(args.reports_dir) if args.reports_dir else repo_root / ".claude" / "evals" / "reports"
    records_path = Path(args.records) if args.records else repo_root / ".claude" / "evals" / "calibration-records.json"

    floors = load_floors(floors_path)
    quarantined = load_quarantine(quarantine_path)
    targets = [args.agent] if args.agent else target_universe(dirs)

    all_pairs: List[str] = []
    for t in targets:
        all_pairs.extend(fixtures_for_target(t, dirs))
    preflight = cost_preflight(all_pairs, dirs, cache_path, routing_path, ladder_path)
    worst_case, hits, net = preflight
    print(f"cost preflight: {net} dispatch(es) worst-case "
          f"({worst_case} fixtures x bands - {hits} cache hit(s))")

    dispatch_fn = lambda pair, model: real_dispatch_fn(pair, model, dirs)  # noqa: E731
    pass_rate_fn = make_pass_rate_fn(dispatch_fn)

    results = []
    for t in targets:
        results.append(calibrate_target(t, dirs, floors, quarantined, pass_rate_fn,
                                         routing_path, ladder_path))

    rhash = routing_hash(routing_path, ladder_path if ladder_path.exists() else None)
    records = load_records(records_path)
    for r in results:
        if r["verdict"] != "uncalibratable":
            records[r["target"]] = build_record(r, rhash)
    save_records(records_path, records)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    report = render_report(results, timestamp, preflight)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{timestamp}-calibration.md"
    report_path.write_text(report)
    print(f"report: {report_path}")

    for r in results:
        print(f"  {r['target']}: {r['verdict']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
