#!/usr/bin/env python3
"""orchestrator — red-team pipeline driver.

Runs probe scripts 01-08 in dependency order with global query budget,
rate limit, and audit log. Probes are declared in the AGENTS list below;
each is a module path relative to `probes/`.

Invocations:
    python orchestrator.py                         # full pipeline
    python orchestrator.py --dry-run               # validate config, zero HTTP
    python orchestrator.py --agents 01 02          # run specific probes
    python orchestrator.py --start 03              # resume from probe 03

Environment:
    REDTEAM_AUTHORIZED=1    Required. Set by the /redteam-model wrapper
                            after scope + consent checks pass. Harness
                            refuses to run if unset.
    TARGET_URL, MODEL_ENDPOINT, RATE_LIMIT, etc. — see config.py

Failure policy: a failed probe does NOT halt the pipeline. Its dependents
run without the expected input; the per-probe summary table names the
missing inputs. Mid-run failure writes progress-manifest.json with the
phase token printed as "Resume with --start <phase>".
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add current dir to path so probes/* and lib/* resolve
sys.path.insert(0, str(Path(__file__).resolve().parent))

from . import config  # type: ignore[import-not-found]  # runtime-resolved
from .lib import http_client, result_store  # type: ignore[import-not-found]


@dataclass(frozen=True)
class Agent:
    id: str
    module_path: str  # relative to harness/redteam/probes/
    depends_on: tuple[str, ...] = ()


AGENTS: list[Agent] = [
    Agent("01", "01_api_recon.py"),
    Agent("02", "02_schema_discovery.py", ("01",)),
    Agent("03", "03_feature_sensitivity.py", ("02",)),
    Agent("04", "04_boundary_mapping.py", ("02", "03")),
    Agent("05", "05_evasion_attack.py", ("02", "03", "04")),
    Agent("06", "06_input_validation.py", ("02",)),
    Agent("07", "07_model_extraction.py", ("02", "03")),
    Agent("08", "08_report_generator.py", ("01", "02", "03", "04", "05", "06", "07")),
]


def _import_agent(module_path: str):
    """Dynamic-import a probe module from `probes/<module_path>`.

    Filenames start with digits, so normal import syntax does not apply —
    use importlib.util.spec_from_file_location.
    """
    full = Path(__file__).resolve().parent / "probes" / module_path
    spec = importlib.util.spec_from_file_location(full.stem, full)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load probe {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def run_agent(agent: Agent, dry_run: bool) -> tuple[str, float]:
    """Run one agent, return (status, elapsed_seconds)."""
    start = time.monotonic()
    try:
        if dry_run:
            return ("dry-run", time.monotonic() - start)
        mod = _import_agent(agent.module_path)
        if not hasattr(mod, "run"):
            return ("error: no run()", time.monotonic() - start)
        mod.run()
        result_store.record_completion(agent.id)
        return ("ok", time.monotonic() - start)
    except http_client.QueryBudgetExhausted:
        result_store.record_failure(agent.id, "query_budget_exhausted")
        return ("budget_exhausted", time.monotonic() - start)
    except Exception as e:  # best-effort: do not halt siblings
        result_store.record_failure(agent.id, f"{type(e).__name__}: {e}")
        return (f"error: {type(e).__name__}", time.monotonic() - start)


def dependencies_met(agent: Agent) -> bool:
    completed = set(result_store.list_completed_phases())
    return all(dep in completed for dep in agent.depends_on)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Validate config; make zero HTTP requests.")
    p.add_argument("--agents", nargs="+", metavar="ID",
                   help="Run only these probe IDs (space-separated).")
    p.add_argument("--start", metavar="ID",
                   help="Resume from this probe ID (dependency check skipped).")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Authorization gate — the /redteam-model wrapper sets this env var
    # after scope + consent checks. The harness refuses to run without it.
    if os.environ.get("REDTEAM_AUTHORIZED") != "1" and not args.dry_run:
        print("ERROR: REDTEAM_AUTHORIZED=1 is required.\n"
              "Invoke via the /redteam-model command or export the env var manually\n"
              "only after running the scope + consent checks.",
              file=sys.stderr)
        return 2

    try:
        config.validate()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Reset manifest if starting fresh
    if not args.start and not args.agents:
        result_store.reset()

    # Determine agents to run
    if args.agents:
        selected = [a for a in AGENTS if a.id in args.agents]
    elif args.start:
        ids = [a.id for a in AGENTS]
        if args.start not in ids:
            print(f"ERROR: --start {args.start} not a valid probe ID.", file=sys.stderr)
            return 2
        idx = ids.index(args.start)
        selected = AGENTS[idx:]
    else:
        selected = list(AGENTS)

    # Run
    summary: list[tuple[str, str, float]] = []
    for agent in selected:
        # Dependency check — only when running full pipeline (not --agents / --start)
        if not args.agents and not args.start:
            if not dependencies_met(agent):
                summary.append((agent.id, "skipped (deps missing)", 0.0))
                continue

        status, elapsed = run_agent(agent, args.dry_run)
        summary.append((agent.id, status, elapsed))

        if status.startswith("error") or status == "budget_exhausted":
            print(f"  {result_store.resume_message(agent.id)}", file=sys.stderr)

    # Summary table
    print("\nRed-team run summary:")
    print("  Probe  Status                     Elapsed")
    for aid, status, elapsed in summary:
        print(f"  {aid:5}  {status:26}  {elapsed:.2f}s")

    # Exit code: non-zero if any probe failed outright (not budget or dry-run)
    any_hard_error = any(s.startswith("error") for _, s, _ in summary)
    return 1 if any_hard_error else 0


if __name__ == "__main__":
    # When invoked as a script (not via `python -m`), the relative imports
    # above fail. Re-invoke ourselves via the package path so imports resolve.
    pkg = Path(__file__).resolve().parent.name
    if __package__ is None or __package__ == "":
        parent = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(parent))
        # Re-exec as module
        os.execvp(sys.executable, [sys.executable, "-m", f"{pkg}.orchestrator", *sys.argv[1:]])
    sys.exit(main())
