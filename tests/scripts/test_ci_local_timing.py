"""Tests for scripts/ci-local.sh's opt-in per-step timing instrument
(CI_LOCAL_TIMING) and its pure render helper scripts/lib/ci-timing.sh.

Issue #1118. scripts/ci-local.sh stays bash (a sanctioned repo-root orchestration
script, out of the Python-only rule per ADR 0014/0015); only the test harness is
pytest, matching tests/scripts/test_ci_local_hermetic.py.

Two layers of coverage:
  * End-to-end: invoke ci-local.sh with a fast, hermetic --only selection and
    assert the timing section appears/does not appear and exit codes/summary are
    unchanged. chk_oe_staleness is advisory (--warn-only, always exit 0).
  * Unit: source scripts/lib/ci-timing.sh in bash and seed a fake $RUNDIR to test
    the pure renderer deterministically — no real suite run, no timing flakiness.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from _repo_root import REPO_ROOT

CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"
CI_TIMING_LIB = REPO_ROOT / "scripts" / "lib" / "ci-timing.sh"

TIMING_HEADER = "== timing =="
TOTAL_RE = re.compile(r"^\s*total\s+(\d+\.\d{2})s\s*$", re.MULTILINE)


def _base_env() -> dict:
    """Minimal, deterministic env. PATH so real tools resolve; HOME for tools
    that read it; C locale for stable output. CI_LOCAL_PROBE_ENV must be absent
    or ci-local short-circuits before running anything."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C",
        "LC_ALL": "C",
    }
    return env


def _run_ci_local(*args: str, timing: str | None) -> subprocess.CompletedProcess:
    """Run ci-local.sh with the given args. `timing` sets CI_LOCAL_TIMING to that
    value, or leaves it unset when None."""
    env = _base_env()
    if timing is not None:
        env["CI_LOCAL_TIMING"] = timing
    return subprocess.run(
        ["bash", str(CI_LOCAL), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# --- Step 1.1: total run wall-clock, strict flag semantics -----------------


def test_timing_absent_when_flag_unset() -> None:
    proc = _run_ci_local("--only=chk_oe_staleness", timing=None)
    assert proc.returncode == 0, proc.stderr
    assert TIMING_HEADER not in proc.stdout
    assert "All local CI checks passed." in proc.stdout


def test_timing_absent_for_non_enabling_values() -> None:
    # Criterion 1: any value other than exactly "1" is off (0, false, empty).
    for value in ("0", "false", ""):
        proc = _run_ci_local("--only=chk_oe_staleness", timing=value)
        assert proc.returncode == 0, f"value={value!r}: {proc.stderr}"
        assert TIMING_HEADER not in proc.stdout, f"value={value!r} rendered timing"
        assert "All local CI checks passed." in proc.stdout


def test_timing_section_reports_positive_total_when_enabled() -> None:
    proc = _run_ci_local("--only=chk_oe_staleness", timing="1")
    assert proc.returncode == 0, proc.stderr
    assert TIMING_HEADER in proc.stdout
    match = TOTAL_RE.search(proc.stdout)
    assert match is not None, f"no well-formed total line in:\n{proc.stdout}"
    assert float(match.group(1)) > 0.0


def test_enabling_timing_does_not_change_exit_or_summary() -> None:
    off = _run_ci_local("--only=chk_oe_staleness", timing=None)
    on = _run_ci_local("--only=chk_oe_staleness", timing="1")
    assert off.returncode == on.returncode == 0
    assert "All local CI checks passed." in off.stdout
    assert "All local CI checks passed." in on.stdout


# --- Step 1.2: per-check wall-clock in declared order + machine block -------

PER_CHECK_RE = re.compile(r"^\s*(\S.*?)\s+(\d+\.\d{2})s\s*$")


def _render_helper(rundir: Path, *labels: str) -> str:
    """Source ci-timing.sh and invoke the pure renderer against a seeded rundir."""
    script = f'source "{CI_TIMING_LIB}"; ci_render_timing "{rundir}" ' + " ".join(labels)
    proc = subprocess.run(
        ["bash", "-c", script], env=_base_env(), capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_helper_renders_each_label_with_its_own_seeded_time(tmp_path: Path) -> None:
    # Distinct values, seeded so index i -> i.time; proves the label<->time mapping
    # is by index and that no per-check value is copied from the total (no swap).
    (tmp_path / ".total.time").write_text("9.99\n")
    (tmp_path / "0.time").write_text("1.11\n")
    (tmp_path / "1.time").write_text("2.22\n")
    (tmp_path / "2.time").write_text("3.33\n")

    out = _render_helper(tmp_path, "chk_a", "chk_b", "chk_c")

    human, _, machine = out.partition("-- machine-readable --")

    # Human section: labels appear in the declared (argument) order, each with its
    # own seeded value; none copies the total.
    assert human.index("chk_a") < human.index("chk_b") < human.index("chk_c")
    assert re.search(r"^\s*chk_a\s+1\.11s$", human, re.MULTILINE)
    assert re.search(r"^\s*chk_b\s+2\.22s$", human, re.MULTILINE)
    assert re.search(r"^\s*chk_c\s+3\.33s$", human, re.MULTILINE)
    assert re.search(r"^\s*total\s+9\.99s$", human, re.MULTILINE)

    # Machine block: uncolored label<TAB>seconds (no 's' suffix, no ANSI), one per
    # check plus total, same declared order.
    assert "chk_a\t1.11" in machine
    assert "chk_b\t2.22" in machine
    assert "chk_c\t3.33" in machine
    assert "total\t9.99" in machine
    assert "\x1b[" not in machine  # no ANSI colour codes in the machine block


def test_two_concurrent_checks_appear_once_in_declared_order(tmp_path: Path) -> None:
    # Integration: two fast, always-exit-0 checks that dispatch concurrently. Each
    # gets a well-formed per-check time in declared CHECKS order; total > 0. (A
    # near-instant check may legitimately read 0.00s, so per-check is asserted
    # well-formed, not > 0 — the > 0 / distinctness proof lives in the unit test.)
    proc = _run_ci_local("--only=chk_oe_staleness,chk_eval_semver", timing="1")
    assert proc.returncode == 0, proc.stderr
    section = proc.stdout.split(TIMING_HEADER, 1)[1]

    oe_label = "OE scoring staleness (advisory; oe_scoring_staleness.py)"
    semver_label = "eval-corpus semver contract"
    # Declared CHECKS order places OE staleness before the semver contract.
    assert section.index(oe_label) < section.index(semver_label)

    per_check = {
        m.group(1): m.group(2)
        for m in (PER_CHECK_RE.match(line) for line in section.splitlines())
        if m
    }
    assert oe_label in per_check and re.fullmatch(r"\d+\.\d{2}", per_check[oe_label])
    assert semver_label in per_check and re.fullmatch(r"\d+\.\d{2}", per_check[semver_label])

    total_match = TOTAL_RE.search(section)
    assert total_match is not None and float(total_match.group(1)) > 0.0


def test_check_set_and_order_identical_with_and_without_flag() -> None:
    off = _run_ci_local("--only=chk_oe_staleness,chk_eval_semver", timing=None)
    on = _run_ci_local("--only=chk_oe_staleness,chk_eval_semver", timing="1")
    assert off.returncode == on.returncode == 0
    # The section headers (one per check, printed by the aggregation loop) are the
    # check set + order; they must be identical whether or not timing is enabled.
    def headers(text):
        return [ln for ln in text.splitlines() if ln.startswith("\x1b[1m== ")]

    assert headers(off.stdout) == headers(on.stdout)


# --- Step 1.3: skip sentinel, failure (exit code), empty selection ---------


def _fabricate_range(*paths: str) -> tuple[str, str]:
    """Create two commit objects (no ref/HEAD/index/worktree mutation) whose diff
    is exactly `paths`, and return (base_sha, head_sha). Lets --changed-only run
    against a deterministic change set regardless of the (dirty) working tree."""

    # Explicit committer/author identity so `git commit-tree` works in a hermetic
    # CI clone that has no user.name/user.email configured (locally it would fall
    # back to the developer's global identity; CI has none → exit 128).
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "ci-timing-test",
        "GIT_AUTHOR_EMAIL": "ci-timing-test@example.invalid",
        "GIT_COMMITTER_NAME": "ci-timing-test",
        "GIT_COMMITTER_EMAIL": "ci-timing-test@example.invalid",
    }

    def git(*args: str, stdin: str | None = None) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            input=stdin,
            capture_output=True,
            text=True,
            check=True,
            env=git_env,
        ).stdout.strip()

    blob = git("hash-object", "-w", "--stdin", stdin="x\n")
    tree_spec = "".join(f"100644 blob {blob}\t{p}\n" for p in paths)
    tree = git("mktree", stdin=tree_spec)
    empty_tree = git("mktree", stdin="")
    base = git("commit-tree", empty_tree, "-m", "base")
    head = git("commit-tree", tree, "-p", base, "-m", "head")
    return base, head


def test_helper_shows_skipped_sentinel_and_still_times_failures(tmp_path: Path) -> None:
    # index 0: ran & passed; index 1: ran & FAILED (rc=1) but still timed;
    # index 2: skipped (rc present, no .time) — must read 'skipped', never 0.00s.
    (tmp_path / ".total.time").write_text("5.00\n")
    (tmp_path / "0.time").write_text("1.00\n")
    (tmp_path / "0.rc").write_text("0\n")
    (tmp_path / "1.time").write_text("2.00\n")
    (tmp_path / "1.rc").write_text("1\n")
    (tmp_path / "2.rc").write_text("0\n")  # deliberately no 2.time

    out = _render_helper(tmp_path, "chk_a", "chk_b", "chk_c")
    human, _, machine = out.partition("-- machine-readable --")

    assert re.search(r"^\s*chk_a\s+1\.00s$", human, re.MULTILINE)
    assert re.search(r"^\s*chk_b\s+2\.00s$", human, re.MULTILINE)  # failing, still timed
    assert re.search(r"^\s*chk_c\s+skipped$", human, re.MULTILINE)  # not 0.00s
    assert "0.00" not in human
    assert "chk_c\tskipped" in machine


def test_helper_normalizes_seconds_and_falls_back_to_question_mark(tmp_path: Path) -> None:
    # Pin the renderer's reason to exist — %R normalization to exactly two
    # decimals — and its sentinel/robustness branches:
    #   index 0: under-precision "1.2"      -> "1.20s"
    #   index 1: over-precision  "0.007"    -> "0.01s" (rounds)
    #   index 2: garbage .time (has .rc)    -> "?"      (non-numeric, not "skipped")
    #   index 3: neither .time nor .rc      -> "?"
    #   total:   stray leading line         -> tail -1 picks the real value
    (tmp_path / ".total.time").write_text("junk line\n3.5\n")
    (tmp_path / "0.time").write_text("1.2\n")
    (tmp_path / "0.rc").write_text("0\n")
    (tmp_path / "1.time").write_text("0.007\n")
    (tmp_path / "1.rc").write_text("0\n")
    (tmp_path / "2.time").write_text("notanumber\n")
    (tmp_path / "2.rc").write_text("0\n")
    # index 3: deliberately no files at all

    out = _render_helper(tmp_path, "chk_a", "chk_b", "chk_c", "chk_d")
    human, _, machine = out.partition("-- machine-readable --")

    assert re.search(r"^\s*chk_a\s+1\.20s$", human, re.MULTILINE)  # padded
    assert re.search(r"^\s*chk_b\s+0\.01s$", human, re.MULTILINE)  # rounded
    assert re.search(r"^\s*chk_c\s+\?$", human, re.MULTILINE)  # garbage -> ?
    assert re.search(r"^\s*chk_d\s+\?$", human, re.MULTILINE)  # missing -> ?
    assert re.search(r"^\s*total\s+3\.50s$", human, re.MULTILINE)  # tail -1 of a stray line
    assert "chk_c\t?" in machine
    assert "chk_d\t?" in machine


def test_failing_check_preserves_nonzero_exit_and_shows_timing(tmp_path: Path) -> None:
    # A shellcheck stub that exits 1 makes chk_shellcheck_helpers fail deterministically
    # on every OS. The appended timing section must not swallow the non-zero verdict.
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "shellcheck").write_text("#!/bin/sh\nexit 1\n")
    (stub / "shellcheck").chmod(0o755)

    env = _base_env()
    env["PATH"] = f"{stub}{os.pathsep}{env['PATH']}"
    # shellcheck is version-pinned, so ci-local.sh deliberately ignores a PATH
    # stub (SHELLCHECK_VERSION / _resolve_shellcheck). Point the gate at the
    # stub explicitly — this now stubs exactly the binary the check runs,
    # rather than one it might happen to pick up.
    env["SHELLCHECK_BIN"] = str(stub / "shellcheck")
    env["CI_LOCAL_TIMING"] = "1"
    proc = subprocess.run(
        ["bash", str(CI_LOCAL), "--only=chk_shellcheck_helpers"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    section = proc.stdout.split(TIMING_HEADER, 1)
    assert len(section) == 2, "timing section missing on a failing run"
    assert PER_CHECK_RE.search(
        next(ln for ln in section[1].splitlines() if "shellcheck" in ln)
    ), "failing check has no timing line"


def test_empty_only_selection_exits_2_without_timing() -> None:
    proc = _run_ci_local("--only=chk_does_not_exist", timing="1")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert TIMING_HEADER not in proc.stdout


def test_changed_only_skip_renders_sentinel_and_keeps_selection() -> None:
    # Change set touches only foo.txt: chk_eslint (watches plugins/dev-team, *.js/…)
    # is skipped; chk_oe_staleness (no watched path) always runs.
    base, head = _fabricate_range("foo.txt")
    args = ("--only=chk_oe_staleness,chk_eslint", "--changed-only", base, head)
    on = _run_ci_local(*args, timing="1")
    off = _run_ci_local(*args, timing=None)
    assert on.returncode == off.returncode == 0, on.stderr

    section = on.stdout.split(TIMING_HEADER, 1)[1]
    assert re.search(r"^\s*eslint\s+skipped$", section, re.MULTILINE)
    assert "0.00" not in section  # the skip is never a zero duration
    oe = "OE scoring staleness (advisory; oe_scoring_staleness.py)"
    oe_line = next(ln for ln in section.splitlines() if oe in ln)
    assert re.search(r"\d+\.\d{2}s$", oe_line)  # oe actually ran

    # Selection (the per-check section headers) is identical with/without timing.
    def headers(t):
        return [ln for ln in t.splitlines() if ln.startswith("\x1b[1m== ")]

    assert headers(on.stdout) == headers(off.stdout)


def test_base_head_is_a_distinct_mode_from_changed_only() -> None:
    # With a BASE/HEAD range (no --changed-only, no --only filter interplay),
    # chk_eval_semver runs its real classifier; without a range it takes its own
    # internal skip-print. Isolates BASE/HEAD from --changed-only.
    base, head = _fabricate_range("foo.txt")
    with_range = _run_ci_local("--only=chk_eval_semver", base, head, timing="1")
    no_range = _run_ci_local("--only=chk_eval_semver", timing="1")

    skip_msg = "skipped (no BASE/HEAD range supplied)"
    assert with_range.returncode == 0, with_range.stdout  # classifier ran clean
    assert skip_msg not in with_range.stdout  # it actually executed
    assert skip_msg in no_range.stdout  # it took the internal skip-print

    section = with_range.stdout.split(TIMING_HEADER, 1)[1]
    semver_line = next(ln for ln in section.splitlines() if "eval-corpus semver" in ln)
    assert re.search(r"\d+\.\d{2}s$", semver_line)  # real timing, not a sentinel
