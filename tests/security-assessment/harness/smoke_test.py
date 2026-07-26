#!/usr/bin/env python3
"""Lightweight smoke test for the security-assessment red-team harness.

Guards the bootstrap + probe-loader wiring fixed alongside this file — the
class of bug where the orchestrator's package-relative imports (and the
probes' own `from .. import config`) do not resolve, so the harness cannot
run at all. It is deliberately cheap: it exercises import/dispatch wiring and
the zero-HTTP `--dry-run` path, never a live probe run, so the only runtime
dependency is `httpx` (numpy/scipy/scikit-learn are used lazily inside probe
`run()` bodies, which this test never reaches).

Checks:
  1. `python3 orchestrator.py --dry-run` exits 0 from an arbitrary working
     directory (the self-bootstrap re-execs as a module so relative imports
     resolve regardless of cwd).
  2. `python3 -m redteam.orchestrator --dry-run` exits 0 — parity with (1).
  3. Every probe module loads via the orchestrator's loader, proving each
     probe's `from .. import config` / `from ..lib import ...` resolves.
  4. A real (non-dry-run) invocation refuses without REDTEAM_AUTHORIZED=1.

Run: python3 tests/security-assessment/harness/smoke_test.py
Exit: 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS = REPO_ROOT / "plugins" / "security-assessment" / "harness"
ORCH = HARNESS / "redteam" / "orchestrator.py"
PROBES = HARNESS / "redteam" / "probes"

FAILED = 0


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    global FAILED
    FAILED += 1
    print(f"  FAIL: {msg}", file=sys.stderr)


def _run(cmd: list[str], *, cwd: Path, env_extra: dict[str, str]):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        cmd, cwd=str(cwd), env=env, check=False, capture_output=True, text=True, timeout=60
    )


def check_plain_script_dry_run() -> None:
    # Run from a throwaway cwd so a working bootstrap is the only way imports
    # can resolve (cwd is NOT the harness dir).
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(
            [sys.executable, str(ORCH), "--dry-run"],
            cwd=Path(tmp),
            env_extra={"TARGET_URL": "http://127.0.0.1:8000"},
        )
    if r.returncode != 0:
        fail(f"`orchestrator.py --dry-run` exited {r.returncode}\n{r.stderr}")
        return
    if "Red-team run summary" not in r.stdout or "dry-run" not in r.stdout:
        fail(f"`orchestrator.py --dry-run` produced unexpected output:\n{r.stdout}")
        return
    ok("plain-script --dry-run self-bootstraps and exits 0 from an arbitrary cwd")


def check_module_dry_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(
            [sys.executable, "-m", "redteam.orchestrator", "--dry-run"],
            cwd=Path(tmp),
            env_extra={
                "TARGET_URL": "http://127.0.0.1:8000",
                "PYTHONPATH": str(HARNESS),
            },
        )
    if r.returncode != 0:
        fail(f"`python -m redteam.orchestrator --dry-run` exited {r.returncode}\n{r.stderr}")
        return
    ok("module-form --dry-run exits 0 (parity with plain script)")


def check_probes_load() -> None:
    sys.path.insert(0, str(HARNESS))
    os.environ.setdefault("TARGET_URL", "http://127.0.0.1:8000")
    try:
        from redteam import orchestrator
    except Exception as e:  # noqa: BLE001 - any import error is itself the failure this smoke test reports; pragma: no cover
        fail(f"could not import redteam.orchestrator: {type(e).__name__}: {e}")
        return

    probe_files = sorted(p.name for p in PROBES.glob("probe_[0-9]*.py"))
    if not probe_files:
        fail(f"no probe modules found under {PROBES}")
        return
    bad = []
    for name in probe_files:
        try:
            mod = orchestrator._import_agent(name)
            if not hasattr(mod, "run"):
                bad.append(f"{name} (no run())")
        except Exception as e:  # noqa: BLE001 - any load error is itself the failure this smoke test reports
            bad.append(f"{name} ({type(e).__name__}: {e})")
    if bad:
        fail("probe modules failed to load: " + "; ".join(bad))
        return
    ok(f"all {len(probe_files)} probe modules load and expose run()")


def check_auth_gate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {"TARGET_URL": "http://127.0.0.1:8000"}
        env.pop("REDTEAM_AUTHORIZED", None)
        r = _run(
            [sys.executable, str(ORCH), "--agents", "01"],
            cwd=Path(tmp),
            env_extra=env,
        )
    if r.returncode != 2 or "REDTEAM_AUTHORIZED" not in (r.stdout + r.stderr):
        fail(
            "real run without REDTEAM_AUTHORIZED should refuse with exit 2; "
            f"got exit {r.returncode}\n{r.stdout}{r.stderr}"
        )
        return
    ok("real run refuses without REDTEAM_AUTHORIZED=1 (exit 2)")


def main() -> int:
    if not ORCH.is_file():
        print(f"smoke_test: orchestrator not found at {ORCH}", file=sys.stderr)
        return 1
    print("=== red-team harness smoke test ===")
    check_plain_script_dry_run()
    check_module_dry_run()
    check_probes_load()
    check_auth_gate()
    if FAILED:
        print(f"=== FAILED: {FAILED} check(s) ===", file=sys.stderr)
        return 1
    print("=== all harness smoke checks passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
