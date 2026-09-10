"""Unit tests for hooks/internal_double_gate.py (#2128).

Covers: trigger detection, the fail-on-purpose block path, the three
silent-pass shapes (no doubles / all waived / empty diff), the two distinct
setup-failure advisory paths (base-ref resolution fails; the branch-diff git
call itself fails independently of that), the degraded-import fallback,
multi-finding message enumeration, and the bypass + audit-log path.

Mirrors `test_pre_pr_review.py`'s structure (hermetic git fixtures via
`tests/lib/hermetic.hermetic_git_env`, a subprocess `_run()` helper, and a
direct `importlib` exec of the hook module for tests that need to call
`_evaluate()` without going through stdin/exit).
"""

from __future__ import annotations

import importlib.util as _importlib_util
import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "internal_double_gate.py"

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_gate_spec = _importlib_util.spec_from_file_location("internal_double_gate_direct", _HOOK)
assert _gate_spec is not None and _gate_spec.loader is not None
_gate = _importlib_util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(_gate)


def _run(payload: dict, cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    if extra_env:
        proc_env.update(extra_env)
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _base_repo(tmp_path: Path) -> Path:
    """`main` with one commit: a first-party class + an inert test file.
    The caller checks out `feature` and adds whatever the test needs."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "gateway.py").write_text("class SmtpGateway:\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_old.py").write_text("# nothing doubled here\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def _pr_create_payload(cwd: str) -> dict:
    return {"tool_input": {"command": "gh pr create --title x --body y"}, "cwd": cwd}


# --- Trigger detection --------------------------------------------------------


def test_non_pr_create_command_is_never_evaluated(tmp_path):
    repo = _base_repo(tmp_path)
    result = _run({"tool_input": {"command": "git status"}, "cwd": str(repo)}, repo)

    assert result.returncode == 0
    assert result.stdout == ""


# --- Silent-pass paths --------------------------------------------------------


def test_silent_pass_no_doubles_at_all(tmp_path):
    repo = _base_repo(tmp_path)
    env = hermetic_git_env(home=repo)
    (repo / "tests" / "test_new.py").write_text("assert 1 == 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a clean test"], cwd=repo, env=env, check=True)

    result = _run(_pr_create_payload(str(repo)), repo)

    assert result.returncode == 0
    assert result.stdout == ""


def test_silent_pass_every_double_waived(tmp_path):
    repo = _base_repo(tmp_path)
    env = hermetic_git_env(home=repo)
    (repo / "tests" / "test_new.py").write_text(
        "# double-waiver: B1 — holds the socket\n"
        "m = MagicMock(spec=SmtpGateway)\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a waived double"], cwd=repo, env=env, check=True)

    result = _run(_pr_create_payload(str(repo)), repo)

    assert result.returncode == 0
    assert result.stdout == ""


def test_silent_pass_empty_diff(tmp_path):
    repo = _base_repo(tmp_path)
    # `feature` was just checked out from `main` with no commits of its own.
    result = _run(_pr_create_payload(str(repo)), repo)

    assert result.returncode == 0
    assert result.stdout == ""


# --- The fail-on-purpose block path -------------------------------------------


def test_block_on_unwaived_high_finding_in_the_diff(tmp_path):
    """Fail-on-purpose proof (CLAUDE.md: "make a new gate fail on purpose
    once before trusting it"): a real unwaived double, added only in the
    diff, against a first-party class declared in the UNCHANGED base commit
    — this is also the false-negative regression guard for analyze()'s
    full-tree first-party resolution staying untouched."""
    repo = _base_repo(tmp_path)
    env = hermetic_git_env(home=repo)
    (repo / "tests" / "test_new.py").write_text("m = MagicMock(spec=SmtpGateway)\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add an unwaived double"], cwd=repo, env=env, check=True)

    result = _run(_pr_create_payload(str(repo)), repo)

    assert result.returncode == 2
    assert "SmtpGateway" in result.stdout
    assert "test_new.py" in result.stdout
    assert "Recall bounds" in result.stdout
    assert "Plugin content & hooks" in result.stdout
    assert result.stderr == result.stdout


def test_multi_finding_message_enumeration(tmp_path):
    repo = _base_repo(tmp_path)
    env = hermetic_git_env(home=repo)
    (repo / "src" / "sms.py").write_text("class SmsGateway:\n    pass\n")
    (repo / "tests" / "test_new.py").write_text(
        "m1 = MagicMock(spec=SmtpGateway)\n"
        "m2 = MagicMock(spec=SmtpGateway)\n"
    )
    (repo / "tests" / "test_other.py").write_text("m3 = MagicMock(spec=SmsGateway)\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add three doubles"], cwd=repo, env=env, check=True)

    result = _run(_pr_create_payload(str(repo)), repo)

    assert result.returncode == 2
    assert result.stdout.count("mock_construct of 'SmtpGateway'") == 2
    assert result.stdout.count("mock_construct of 'SmsGateway'") == 1


# --- Setup-failure advisory paths (always fail open to no-block) -------------


def test_base_ref_resolution_failure_is_advisory_and_passes(tmp_path):
    """No `main`/`master` branch exists at all, so `default_base_ref`
    returns None — the gate must never block on its own setup failure."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "solo"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "solo commit"], cwd=tmp_path, env=env, check=True)

    result = _run(_pr_create_payload(str(tmp_path)), tmp_path)

    assert result.returncode == 0
    assert "ADVISORY" in result.stdout
    assert "base ref" in result.stdout


def test_git_diff_failure_after_base_ref_resolves_never_falls_back_to_blocking(tmp_path):
    """`main` exists (so `default_base_ref` resolves it), but `feature` is
    an orphan branch sharing no history with `main` — `git diff
    main...HEAD` has no merge-base and fails. Even though the unscoped
    findings would include a real unwaived double, the hook must NOT block
    on them: it fails open, exactly like the base-ref-failure case."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True)

    subprocess.run(["git", "checkout", "-q", "--orphan", "feature"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "gateway.py").write_text("class SmtpGateway:\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_new.py").write_text("m = MagicMock(spec=SmtpGateway)\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "orphan root with an unwaived double"], cwd=tmp_path, env=env, check=True)

    result = _run(_pr_create_payload(str(tmp_path)), tmp_path)

    assert result.returncode == 0
    assert "ADVISORY" in result.stdout


def test_degraded_import_fallback_never_crashes():
    """Simulates the detector module being unimportable WITHOUT touching
    the shared file on disk (deleting it would race under this repo's
    `pytest -n auto --dist loadgroup` config against any sibling test in
    this same session that spawns a subprocess reading it fresh — the same
    shared-real-file hazard `test_boundary_events.py`'s `xdist_group` marks
    already document). Binding a module name to `None` in `sys.modules` is
    the standard, process-local way to force Python's import machinery to
    raise `ImportError` unconditionally for that name — no filesystem
    mutation, no cross-worker race."""
    sys.modules["internal_double_detector"] = None  # type: ignore[assignment]
    try:
        spec = _importlib_util.spec_from_file_location(
            "internal_double_gate_degraded", _HOOK
        )
        mod = _importlib_util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        exit_code, message = mod._evaluate(".", "origin/main")
    finally:
        sys.modules.pop("internal_double_detector", None)

    assert exit_code == 0
    assert "unavailable" in message


# --- Bypass + audit log -------------------------------------------------------


def test_bypass_allows_and_logs_audit(tmp_path):
    repo = _base_repo(tmp_path)
    env = hermetic_git_env(home=repo)
    (repo / "tests" / "test_new.py").write_text("m = MagicMock(spec=SmtpGateway)\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add an unwaived double"], cwd=repo, env=env, check=True)

    result = _run(
        _pr_create_payload(str(repo)),
        repo,
        extra_env={"INTERNAL_DOUBLE_GATE_BYPASS_REASON": "legitimate exception, tracked in #9999"},
    )

    assert result.returncode == 0
    audit_log = repo / ".claude" / "metrics" / "gate-bypass-audit.jsonl"
    assert audit_log.is_file()
    entry = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["triggeredBy"] == "INTERNAL_DOUBLE_GATE_BYPASS_REASON"
    assert entry["hook"] == "internal_double_gate"


# --- _evaluate() core, direct (no stdin/exit) ---------------------------------


def test_evaluate_returns_advisory_tuple_on_none_base_ref():
    exit_code, message = _gate._evaluate(".", None)

    assert exit_code == 0
    assert "ADVISORY" in message
