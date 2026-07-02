#!/usr/bin/env python3
"""Scope-enforcement test for the red-team harness (issue #732).

Proves that `config.validate()` — and therefore `orchestrator.py main()`,
which calls it before running any probe — actually enforces the
"self-owned targets only" safety boundary via `lib/scope_check.is_self_owned`,
rather than relying solely on prose in ORCHESTRATION.md and the
`REDTEAM_AUTHORIZED` env var (which any caller can set directly, with no
scope check ever having run).

Checks:
  1. `config.validate()` refuses a public TARGET_URL with no self-cert
     artifact (exit non-zero, "SCOPE VIOLATION" on stderr).
  2. `config.validate()` proceeds for a self-owned TARGET_URL (127.0.0.1)
     with no self-cert needed (exit 0).
  3. `config.validate()` proceeds for a public TARGET_URL when
     SELF_CERTIFY_OWNED points at a real artifact, and appends a
     `self_cert` entry to `results/audit_log.jsonl` with the artifact's
     correct SHA-256.
  4. `config.validate()` refuses a public TARGET_URL when SELF_CERTIFY_OWNED
     points at a nonexistent path ("Self-cert artifact not found").
  5. End-to-end: `orchestrator.py --dry-run` refuses a public TARGET_URL
     with no self-cert (exit 2, scope-violation message) — proving the
     enforcement is wired through the real entry point, not just callable
     in isolation.
  6. End-to-end: `orchestrator.py --dry-run` still succeeds for a
     self-owned TARGET_URL (exit 0) — the fix must not break the existing
     happy path.

Run: python3 tests/security-assessment/harness/scope_enforcement_test.py
Exit: 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS = REPO_ROOT / "plugins" / "security-assessment" / "harness"
ORCH = HARNESS / "redteam" / "orchestrator.py"
RESULTS_DIR = HARNESS / "redteam" / "results"
AUDIT_LOG = RESULTS_DIR / "audit_log.jsonl"

PUBLIC_TARGET = "http://8.8.8.8"  # literal public IP; no DNS resolution needed
SELF_OWNED_TARGET = "http://127.0.0.1:8000"

FAILED = 0


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    global FAILED
    FAILED += 1
    print(f"  FAIL: {msg}", file=sys.stderr)


def _reset_audit_log() -> None:
    if AUDIT_LOG.exists():
        AUDIT_LOG.unlink()


def _run_validate(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(HARNESS), env.get("PYTHONPATH", "")) if p
    )
    return subprocess.run(
        [sys.executable, "-c", "from redteam import config; config.validate()"],
        cwd=str(HARNESS),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _run_orchestrator(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra)
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, str(ORCH), "--dry-run"],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )


def check_public_target_refused() -> None:
    _reset_audit_log()
    r = _run_validate({"TARGET_URL": PUBLIC_TARGET})
    if r.returncode == 0:
        fail(
            "config.validate() must refuse a public TARGET_URL with no "
            f"self-cert; it exited 0 instead.\nstdout={r.stdout}\nstderr={r.stderr}"
        )
        return
    if "SCOPE VIOLATION" not in r.stderr:
        fail(
            "config.validate() refused the public target but did not print "
            f"the scope-violation message.\nstderr={r.stderr}"
        )
        return
    ok("config.validate() refuses a public TARGET_URL with no self-cert")


def check_self_owned_target_proceeds() -> None:
    _reset_audit_log()
    r = _run_validate({"TARGET_URL": SELF_OWNED_TARGET})
    if r.returncode != 0:
        fail(
            "config.validate() must proceed for a self-owned TARGET_URL; "
            f"it exited {r.returncode}.\nstdout={r.stdout}\nstderr={r.stderr}"
        )
        return
    ok("config.validate() proceeds for a self-owned TARGET_URL (127.0.0.1)")


def check_self_cert_allows_public_target() -> None:
    _reset_audit_log()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as artifact:
        artifact.write(
            "# Red-team authorization\n"
            "Target: 8.8.8.8\n"
            "Operator: test-suite\n"
            "Signed: test-suite\n"
        )
        artifact_path = artifact.name
    try:
        expected_sha256 = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
        r = _run_validate(
            {"TARGET_URL": PUBLIC_TARGET, "SELF_CERTIFY_OWNED": artifact_path}
        )
        if r.returncode != 0:
            fail(
                "config.validate() must proceed for a public TARGET_URL when "
                f"a valid self-cert artifact is supplied; exited {r.returncode}.\n"
                f"stdout={r.stdout}\nstderr={r.stderr}"
            )
            return
        if not AUDIT_LOG.exists():
            fail(
                "config.validate() accepted the self-cert but did not write "
                f"an audit log entry to {AUDIT_LOG}"
            )
            return
        entries = [
            json.loads(line) for line in AUDIT_LOG.read_text().splitlines() if line
        ]
        cert_entries = [e for e in entries if e.get("event") == "self_cert"]
        if not cert_entries:
            fail(f"audit log has no self_cert entry: {entries}")
            return
        entry = cert_entries[-1]
        if entry.get("artifact_sha256") != expected_sha256:
            fail(
                "audit log self_cert entry has wrong sha256: "
                f"got {entry.get('artifact_sha256')!r}, expected {expected_sha256!r}"
            )
            return
        if entry.get("target") != PUBLIC_TARGET:
            fail(f"audit log self_cert entry has wrong target: {entry}")
            return
        ok(
            "config.validate() proceeds for a public TARGET_URL with a valid "
            "self-cert artifact and logs the correct SHA-256"
        )
    finally:
        os.unlink(artifact_path)


def check_missing_self_cert_artifact_refused() -> None:
    _reset_audit_log()
    r = _run_validate(
        {
            "TARGET_URL": PUBLIC_TARGET,
            "SELF_CERTIFY_OWNED": "/nonexistent/path/authorization.md",
        }
    )
    if r.returncode == 0:
        fail(
            "config.validate() must refuse when the self-cert artifact path "
            "does not exist; it exited 0 instead."
        )
        return
    if "Self-cert artifact not found" not in (r.stdout + r.stderr):
        fail(
            "config.validate() refused the missing artifact but did not use "
            f"the documented message.\nstdout={r.stdout}\nstderr={r.stderr}"
        )
        return
    ok("config.validate() refuses when the self-cert artifact does not exist")


def check_orchestrator_refuses_public_target_end_to_end() -> None:
    _reset_audit_log()
    r = _run_orchestrator({"TARGET_URL": PUBLIC_TARGET})
    if r.returncode == 0:
        fail(
            "orchestrator.py --dry-run must refuse a public TARGET_URL with "
            f"no self-cert; it exited 0.\nstdout={r.stdout}\nstderr={r.stderr}"
        )
        return
    if "SCOPE VIOLATION" not in (r.stdout + r.stderr):
        fail(
            "orchestrator.py --dry-run refused the public target but did not "
            f"surface the scope-violation message.\nstdout={r.stdout}\nstderr={r.stderr}"
        )
        return
    ok("orchestrator.py --dry-run refuses a public TARGET_URL end-to-end (issue #732)")


def check_orchestrator_proceeds_self_owned_end_to_end() -> None:
    _reset_audit_log()
    r = _run_orchestrator({"TARGET_URL": SELF_OWNED_TARGET})
    if r.returncode != 0:
        fail(
            "orchestrator.py --dry-run must still succeed for a self-owned "
            f"TARGET_URL; it exited {r.returncode}.\nstdout={r.stdout}\nstderr={r.stderr}"
        )
        return
    ok("orchestrator.py --dry-run still proceeds for a self-owned TARGET_URL")


def main() -> int:
    if not ORCH.is_file():
        print(
            f"scope_enforcement_test: orchestrator not found at {ORCH}", file=sys.stderr
        )
        return 1
    print("=== red-team harness scope-enforcement test (#732) ===")
    try:
        check_public_target_refused()
        check_self_owned_target_proceeds()
        check_self_cert_allows_public_target()
        check_missing_self_cert_artifact_refused()
        check_orchestrator_refuses_public_target_end_to_end()
        check_orchestrator_proceeds_self_owned_end_to_end()
    finally:
        _reset_audit_log()
    if FAILED:
        print(f"=== FAILED: {FAILED} check(s) ===", file=sys.stderr)
        return 1
    print("=== all scope-enforcement checks passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
