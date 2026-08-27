#!/usr/bin/env python3
"""csharp_stryker_net_slice_runner.py — first-class slicing + configurable
slice-level parallelism for Stryker.NET (issue #561).

Layers on top of ``csharp_stryker_net_wrapper.py``: the wrapper's
``hide_sln``/``restore_sln``/``build_project`` functions are reused directly,
but the hide/restore ceremony happens **once around the whole parallel
fleet** — not per slice — because only one Stryker instance can safely hide
the shared ``.sln`` at a time (see issue #561 §2.1).

Public API (importable, pure functions first):

    load_slices_config(path) -> list[dict]
    resolve_slice_selection(configured, requested) -> list[dict]
    slice_output_dir(output_root, name) -> Path
    slice_report_path(output_root, name) -> Path
    is_terminal_report(path) -> bool
    partition_terminal_slices(slices, output_root, force) -> (to_run, skipped)
    resolve_total_workers(value, cpu_count) -> int
    total_worker_ceiling_check(total_workers, cores, force) -> (bool, Optional[str])
    resolve_worker_allocation(total_workers, slice_count, parallel_slices, per_slice_concurrency, force) -> (int, int)
    build_slice_stryker_config(base_config, slice_def) -> dict
    write_slice_config(output_root, name, stryker_config) -> Path
    summarize_native_report(native_report) -> dict
    aggregate_slice_summaries(summaries) -> dict
    format_progress_line(order, states) -> str

Refs: #561, #667, #669.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# Reuse the shipped wrapper's hide/restore/build/run primitives so the
# hide-once-around-the-fleet contract composes with the existing
# pre-build-before-hide and signal-safe-run guarantees instead of
# duplicating them.
import csharp_stryker_net_wrapper as wrapper

REQUIRED_SLICE_FIELDS = ("name", "mutate")
# Reserved for #667's within-slice refinements — accepted but not yet acted
# on by this runner. Listed here so a typo in a reserved field still fails
# validation instead of silently doing nothing.
RESERVED_SLICE_FIELDS = ("kind", "mutation-level", "exclude-converged")
KNOWN_SLICE_FIELDS = REQUIRED_SLICE_FIELDS + RESERVED_SLICE_FIELDS


# =============================================================================
# Slice config loading + validation
# =============================================================================
def load_slices_config(path: Path) -> list[dict[str, Any]]:
    """Load and validate the ``slices:`` block from a JSON config file.

    Only ``name`` + ``mutate`` are required per slice (#561's "first cut").
    ``kind`` / ``mutation-level`` / ``exclude-converged`` are accepted and
    passed through (reserved for #667) but not otherwise interpreted here.
    Raises ValueError with an actionable message on any structural problem.
    """
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise ValueError(f"slices config not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"slices config is not valid JSON: {path} ({e})")

    slices = data.get("slices")
    if not isinstance(slices, list) or not slices:
        raise ValueError(
            f'slices config {path} must have a non-empty top-level "slices" array'
        )

    seen_names = set()
    for i, s in enumerate(slices):
        if not isinstance(s, dict):
            raise TypeError(f"slices[{i}] must be an object")
        missing = [f for f in REQUIRED_SLICE_FIELDS if f not in s]
        if missing:
            raise ValueError(
                f"slices[{i}] is missing required field(s): {', '.join(missing)}"
            )
        if s["name"] in seen_names:
            raise ValueError(f"duplicate slice name: {s['name']!r}")
        seen_names.add(s["name"])
    return slices


def resolve_slice_selection(
    configured: Sequence[dict[str, Any]], requested: str
) -> list[dict[str, Any]]:
    """Return the configured slice(s) matching ``--slice <requested>``.

    ``requested == "all"`` returns every configured slice, in config order.
    A named slice must match a configured ``name`` exactly, else ValueError.
    """
    if requested == "all":
        return list(configured)
    for s in configured:
        if s["name"] == requested:
            return [s]
    known = ", ".join(s["name"] for s in configured)
    raise ValueError(f"no slice named {requested!r} in config (known: {known})")


# =============================================================================
# Per-slice output layout
# =============================================================================
def slice_output_dir(output_root: Path, name: str) -> Path:
    return Path(output_root) / f"slice-{name}"


def slice_report_path(output_root: Path, name: str) -> Path:
    return slice_output_dir(output_root, name) / "reports" / "mutation-report.json"


def is_terminal_report(path: Path) -> bool:
    """A report is terminal when it exists, parses as JSON, and has a
    non-empty top-level ``files`` map — Stryker.NET's own JSON-reporter
    shape. A partial file from a crashed run either doesn't parse or has no
    ``files`` entries, so it is never mistaken for a completed run.
    """
    p = Path(path)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    files = data.get("files")
    return isinstance(files, dict) and len(files) > 0


def partition_terminal_slices(
    slices: Sequence[dict[str, Any]], output_root: Path, force: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split ``slices`` into (to_run, skipped). A slice is skipped when its
    report is terminal AND ``--force`` was not passed — resume-by-default.
    """
    if force:
        return list(slices), []
    to_run: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for s in slices:
        report = slice_report_path(output_root, s["name"])
        if is_terminal_report(report):
            skipped.append(s)
        else:
            to_run.append(s)
    return to_run, skipped


# =============================================================================
# Total-worker budget + slice/concurrency split
# =============================================================================
def resolve_total_workers(value: str | None, cpu_count: int | None) -> int:
    """``None``/``"auto"`` -> ``max(2, cores / 2)``; otherwise the given int."""
    if value is None or value == "auto":
        cores = cpu_count or 2
        return max(2, cores // 2)
    return int(value)


def total_worker_ceiling_check(
    total_workers: int, cores: int | None, force: bool
) -> tuple[bool, str | None]:
    """Return ``(allowed, message)``. Refuses (``allowed=False``, an error
    message) a total-worker count over ``cores - 1`` unless ``--force`` is
    set, in which case it is allowed with a warning message instead.
    """
    ceiling = max(1, (cores or 2) - 1)
    if total_workers <= ceiling:
        return True, None
    if force:
        return True, (
            f"warning: --total-workers {total_workers} exceeds the cores-1 "
            f"ceiling ({ceiling}, cores={cores or 2}); proceeding due to --force\n"
        )
    return False, (
        f"error: --total-workers {total_workers} exceeds the cores-1 ceiling "
        f"({ceiling}, cores={cores or 2}); pass --force to override\n"
    )


def default_split(total_workers: int, slice_count: int) -> tuple[int, int]:
    """Allocate slices first (up to the configured slice count), then divide
    the remainder as per-slice concurrency — favours cross-slice parallelism
    over deeper within-slice parallelism (#561 §2 default-split rule).
    """
    parallel_slices = max(1, min(total_workers, slice_count))
    per_slice_concurrency = max(1, total_workers // parallel_slices)
    return parallel_slices, per_slice_concurrency


def resolve_worker_allocation(
    total_workers: int,
    slice_count: int,
    parallel_slices: int | None,
    per_slice_concurrency: int | None,
    force: bool,
) -> tuple[int, int, str | None]:
    """Return ``(parallel_slices, per_slice_concurrency, message)``.

    When both axes are set explicitly, refuse (unless ``--force``) if their
    product exceeds ``total_workers``. When only one axis is set, derive the
    other from ``total_workers``. When neither is set, use the default split.
    """
    if parallel_slices is not None and per_slice_concurrency is not None:
        product = parallel_slices * per_slice_concurrency
        if product > total_workers:
            msg_kind = "warning" if force else "error"
            msg = (
                f"{msg_kind}: --parallel-slices {parallel_slices} x "
                f"--per-slice-concurrency {per_slice_concurrency} = {product} "
                f"exceeds the total-worker ceiling ({total_workers})"
                + (
                    "; proceeding due to --force\n"
                    if force
                    else "; pass --force to override\n"
                )
            )
            return parallel_slices, per_slice_concurrency, msg
        return parallel_slices, per_slice_concurrency, None
    if parallel_slices is not None:
        per_slice_concurrency = max(1, total_workers // parallel_slices)
        return parallel_slices, per_slice_concurrency, None
    if per_slice_concurrency is not None:
        parallel_slices = max(1, total_workers // per_slice_concurrency)
        return parallel_slices, per_slice_concurrency, None
    parallel_slices, per_slice_concurrency = default_split(total_workers, slice_count)
    return parallel_slices, per_slice_concurrency, None


# =============================================================================
# Per-slice Stryker config generation
# =============================================================================
def build_slice_stryker_config(
    base_config: dict[str, Any], slice_def: dict[str, Any]
) -> dict[str, Any]:
    """Merge ``base_config`` with the slice's ``mutate`` glob. Defaults
    ``coverage-analysis`` to ``"perTest"`` per #669's validated
    recommendation, unless the base config already sets it (escape hatch,
    e.g. xunit.v3/MTP projects that must keep it ``"off"``).
    """
    cfg = dict(base_config)
    mutate = slice_def["mutate"]
    cfg["mutate"] = mutate if isinstance(mutate, list) else [mutate]
    cfg.setdefault("coverage-analysis", "perTest")
    return cfg


def write_slice_config(
    output_root: Path, name: str, stryker_config: dict[str, Any]
) -> Path:
    out_dir = slice_output_dir(output_root, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "stryker-config.json"
    path.write_text(json.dumps({"stryker-config": stryker_config}, indent=2))
    return path


# =============================================================================
# Report summarizing + aggregate roll-up
# =============================================================================
def summarize_native_report(native: dict[str, Any]) -> dict[str, int]:
    """Reduce a Stryker.NET native ``mutation-report.json`` (top-level
    ``files`` map of file -> {"mutants": [...]}) to per-status counts.
    """
    counts: dict[str, int] = {}
    for file_entry in native.get("files", {}).values():
        for mutant in file_entry.get("mutants", []):
            status = mutant.get("status", "Unknown")
            counts[status] = counts.get(status, 0) + 1
    return counts


def aggregate_slice_summaries(
    summaries: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Roll up per-slice status counts into one aggregate document."""
    totals: dict[str, int] = {}
    per_slice: dict[str, dict[str, int]] = {}
    for name, counts in summaries.items():
        per_slice[name] = counts
        for status, n in counts.items():
            totals[status] = totals.get(status, 0) + n
    killed = totals.get("Killed", 0)
    survived = totals.get("Survived", 0)
    no_coverage = totals.get("NoCoverage", 0)
    denom = killed + survived + no_coverage
    honest_score = (killed / denom * 100.0) if denom else 0.0
    return {
        "schema_version": 1,
        "tool": "stryker-net",
        "slices": per_slice,
        "totals": totals,
        "honest_score": honest_score,
    }


def write_aggregate_report(output_root: Path, aggregate: dict[str, Any]) -> Path:
    path = Path(output_root) / "aggregate-mutation-report.json"
    path.write_text(json.dumps(aggregate, indent=2))
    return path


# =============================================================================
# Rolled-up progress reporting
# =============================================================================
def format_progress_line(order: Sequence[str], states: dict[str, str]) -> str:
    """Render a rolled-up progress line, e.g.:

    ``slice 3/7 done, slice 4/7 running, slice 5/7 running, slice 6/7 queued``
    """
    total = len(order)
    parts = []
    for i, name in enumerate(order, start=1):
        status = states.get(name, "queued")
        parts.append(f"slice {i}/{total} {status}")
    return ", ".join(parts)


# =============================================================================
# Single-slice run (fleet-level hide/restore already done by the caller)
# =============================================================================
def run_slice(
    slice_def: dict[str, Any],
    *,
    base_config: dict[str, Any],
    output_root: Path,
    stryker_bin: str,
    per_slice_concurrency: int,
) -> int:
    """Write the slice's config, invoke Stryker scoped to it, return the
    Stryker exit code. Does NOT hide/restore ``.sln`` — the fleet caller
    owns that ceremony once for the whole run.
    """
    name = slice_def["name"]
    cfg = build_slice_stryker_config(base_config, slice_def)
    config_path = write_slice_config(output_root, name, cfg)
    out_dir = slice_output_dir(output_root, name)
    logfile = out_dir / "wrapper.log"
    stryker_args = [
        "--config-file",
        str(config_path),
        "-c",
        str(per_slice_concurrency),
        "-O",
        str(out_dir),
    ]
    return wrapper.run_stryker(
        stryker_bin=stryker_bin, stryker_args=stryker_args, logfile=logfile
    )


# =============================================================================
# Main
# =============================================================================
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="csharp_stryker_net_slice_runner.py",
        description=(
            "First-class slicing + configurable slice-level parallelism for "
            "Stryker.NET (#561)."
        ),
    )
    p.add_argument(
        "--slices-config",
        default=os.environ.get("MUTATION_SLICES_CONFIG", "mutation-slices.json"),
        help="Path to the slices config JSON (default: %(default)s)",
    )
    p.add_argument(
        "--slice",
        required=True,
        help='Slice name, or "all" to run every configured slice.',
    )
    p.add_argument(
        "--output-root",
        default=os.environ.get("MUTATION_SLICE_OUTPUT_ROOT", "StrykerOutput"),
        help="Root directory for per-slice output (default: %(default)s)",
    )
    p.add_argument(
        "--sln", default=os.environ.get("SLN", "Foo.sln"), help="Solution file."
    )
    p.add_argument(
        "--shim-project",
        default=os.environ.get("SHIM_PROJECT", ""),
        help="Optional shim test project to pre-build.",
    )
    p.add_argument(
        "--stryker-bin",
        default=os.environ.get("STRYKER_BIN", "dotnet-stryker"),
        help="Stryker executable name (default: %(default)s)",
    )
    p.add_argument(
        "--base-config",
        default=os.environ.get("MUTATION_BASE_CONFIG", ""),
        help="Path to a base stryker-config.json's inner config to merge "
        "into each slice's generated config. Empty = start from {}.",
    )
    p.add_argument(
        "--total-workers",
        default=os.environ.get("MUTATION_TOTAL_WORKERS", "auto"),
        help='Integer, or "auto" = max(2, cores / 2) (default: auto).',
    )
    p.add_argument("--parallel-slices", type=int, default=None)
    p.add_argument("--per-slice-concurrency", type=int, default=None)
    p.add_argument(
        "--force",
        action="store_true",
        help="Rerun terminal slices and override worker-ceiling refusals.",
    )
    return p.parse_args(list(argv))


def _load_base_config(path: str) -> dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    return data.get("stryker-config", data)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    try:
        configured = load_slices_config(Path(args.slices_config))
        selected = resolve_slice_selection(configured, args.slice)
    except (ValueError, TypeError) as e:
        sys.stderr.write(f"error: {e}\n")
        return 2

    output_root = Path(args.output_root)
    to_run, skipped = partition_terminal_slices(selected, output_root, args.force)
    for s in skipped:
        print(f"SKIPPED {s['name']} — terminal report exists (use --force to rerun)")

    if not to_run:
        print("no slices to run (all terminal; pass --force to rerun)")
        return 0

    cores = os.cpu_count()
    total_workers = resolve_total_workers(args.total_workers, cores)
    allowed, msg = total_worker_ceiling_check(total_workers, cores, args.force)
    if msg:
        sys.stderr.write(msg)
    if not allowed:
        return 2

    parallel_slices, per_slice_concurrency, split_msg = resolve_worker_allocation(
        total_workers,
        len(to_run),
        args.parallel_slices,
        args.per_slice_concurrency,
        args.force,
    )
    if split_msg:
        sys.stderr.write(split_msg)
        if split_msg.startswith("error") and not args.force:
            return 2

    base_config = _load_base_config(args.base_config)

    # ---- Fleet-level .sln hide/restore — ONCE, not per slice. ----
    sln = Path(args.sln)
    sln_hidden = Path(f"{args.sln}.stryker-hidden")
    stale_err = wrapper.check_stale_hidden_sln(sln, sln_hidden)
    if stale_err is not None:
        sys.stderr.write(stale_err)
        return wrapper.EXIT_STALE_HIDDEN_SLN

    rc = wrapper.build_project(args.sln)
    if rc != 0:
        return rc
    if args.shim_project:
        rc = wrapper.build_project(args.shim_project)
        if rc != 0:
            return rc

    wrapper.hide_sln(sln, sln_hidden)

    order = [s["name"] for s in to_run]
    states: dict[str, str] = {name: "queued" for name in order}
    exit_codes: dict[str, int] = {}

    # ---- Install signal handlers now that we're about to spawn a fleet of
    # concurrent Stryker subprocesses (one per in-flight slice). This reuses
    # the wrapper's own SIGINT/SIGTERM handler, which terminates every Popen
    # tracked in wrapper._RUNNING_STRYKER_PROCS — a set shared across every
    # ThreadPoolExecutor worker thread below, so Ctrl-C / SIGTERM kills ALL
    # still-running slices, not just one (#732). Save/restore previous
    # handlers exactly as wrapper.main() does, so library-style callers
    # (e.g. pytest) don't inherit our handlers past this call.
    previous_signal_handlers = wrapper._install_signal_handlers()
    interrupted = False
    try:
        with ThreadPoolExecutor(max_workers=max(1, parallel_slices)) as pool:
            futures = {}
            for s in to_run:
                states[s["name"]] = "running"
                futures[
                    pool.submit(
                        run_slice,
                        s,
                        base_config=base_config,
                        output_root=output_root,
                        stryker_bin=args.stryker_bin,
                        per_slice_concurrency=per_slice_concurrency,
                    )
                ] = s["name"]
            print(format_progress_line(order, states))
            for future, name in futures.items():
                exit_codes[name] = future.result()
                states[name] = "done" if exit_codes[name] == 0 else "failed"
                print(format_progress_line(order, states))
    except KeyboardInterrupt:
        # SIGINT/SIGTERM propagated through the signal handlers, which have
        # already terminate()'d every live Stryker subprocess across all
        # slice worker threads. Fall through to fleet-level .sln restoration
        # below rather than let this escape uncaught.
        interrupted = True
        sys.stderr.write("mutation slice run interrupted; restoring .sln\n")
    finally:
        restored = wrapper.restore_sln(sln, sln_hidden)
        if not restored:
            sys.stderr.write(
                f"error: failed to restore {sln} from {sln_hidden} — the "
                "solution file is left hidden/renamed, which will break the "
                "next build (#1955)\n"
            )
        wrapper._restore_signal_handlers(previous_signal_handlers)

    if interrupted:
        return 130

    # ---- Aggregate roll-up ----
    summaries = {}
    for s in to_run:
        report = slice_report_path(output_root, s["name"])
        if report.exists():
            try:
                summaries[s["name"]] = summarize_native_report(
                    json.loads(report.read_text())
                )
            except (json.JSONDecodeError, OSError):
                pass
    if summaries:
        aggregate = aggregate_slice_summaries(summaries)
        write_aggregate_report(output_root, aggregate)

    fleet_rc = max(exit_codes.values(), default=0)
    # Don't clobber a real per-slice failure — surface the restore failure
    # only when every slice otherwise looked clean (#1955).
    if not restored and fleet_rc == 0:
        fleet_rc = wrapper.EXIT_RESTORE_SLN_FAILED
    return fleet_rc


if __name__ == "__main__":
    sys.exit(main())
