"""Tests for scripts/lib/tool-probe.sh — the runtime verification helpers
dev-setup.sh uses to confirm its toolchain actually works.

The bug these exist to prevent: dev-setup.sh verified every tool with
`command -v <tool>`, which asks "is there a file with this name" rather than
"does this tool run". It printed `✓ semgrep` for an install whose native
`_cffi_backend` extension was missing — the binary resolved, and every real
invocation died with a ModuleNotFoundError and a Rust panic. The
security-assessment suites then failed against a toolchain the script had just
called ready.

Per CLAUDE.md, a gate that cannot fail is worse than no gate, and a runtime
property is verified by exercising it at runtime. So these tests do not assert
on the script's text: they source the library and run it against real working,
missing, and crashing commands, checking the outcome the caller actually
depends on (the reported severity and whether FAILURES was incremented).

The three outcomes, and why the middle one is not the interesting one:

- works                -> ok, run not failed
- missing              -> severity is the caller's choice (required vs optional)
- present but crashing -> ALWAYS fails the run, even when the tool is optional.
  Declining to install something is a decision; a tool that is installed and
  crashes is a broken environment. This is the case that used to report green.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

LIB = REPO_ROOT / "scripts" / "lib" / "tool-probe.sh"

# A name no PATH entry can plausibly supply, so the probe hits the shell's
# "command not found" (exit 127) branch.
MISSING = "dev-team-definitely-absent-tool"


def _run(body: str, extra_path: Path | None = None) -> subprocess.CompletedProcess:
    """Source the library and run `body`, echoing the final FAILURES count."""
    env = dict(os.environ)
    if extra_path is not None:
        env["PATH"] = f"{extra_path}{os.pathsep}{env['PATH']}"
    script = f'. "{LIB}"\n{body}\nprintf "FAILURES=%s\\n" "$FAILURES"'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture
def broken_tool(tmp_path: Path) -> Path:
    """A directory containing `brokentool`: on PATH, exits non-zero.

    Reproduces the shape of the semgrep failure that motivated this library —
    resolvable, and fatal on every invocation.
    """
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    tool = bindir / "brokentool"
    tool.write_text(
        "#!/bin/sh\n"
        "echo \"ModuleNotFoundError: No module named '_cffi_backend'\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    return bindir


def test_library_sources_cleanly_and_exposes_the_helpers() -> None:
    result = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; type _probe require_tool optional_tool'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --- outcome 1: the tool works --------------------------------------------


def test_working_required_tool_is_reported_ok_and_does_not_fail_the_run() -> None:
    r = _run('require_tool "python3" "" python3 --version')
    assert "FAILURES=0" in r.stdout, r.stdout + r.stderr
    assert "python3" in r.stdout


def test_working_optional_tool_does_not_fail_the_run() -> None:
    r = _run('optional_tool "python3" "note" python3 --version')
    assert "FAILURES=0" in r.stdout, r.stdout + r.stderr


# --- outcome 2: the tool is absent ----------------------------------------


def test_missing_required_tool_fails_the_run() -> None:
    r = _run(f'require_tool "missing" "declared in requirements-dev.txt" {MISSING} --version')
    assert "FAILURES=1" in r.stdout, r.stdout + r.stderr
    assert "not found" in r.stderr


def test_missing_required_tool_reports_where_the_tool_comes_from() -> None:
    """Both wrappers take a note, so replacing the old hand-written messages
    with the shared helper does not cost the operator the "declared in
    requirements-dev.txt" hint those messages carried."""
    r = _run(f'require_tool "missing" "declared in requirements-dev.txt" {MISSING} --version')
    assert "declared in requirements-dev.txt" in r.stderr, r.stderr


def test_missing_optional_tool_warns_but_does_not_fail_the_run() -> None:
    r = _run(f'optional_tool "missing" "install it if you need it" {MISSING} --version')
    assert "FAILURES=0" in r.stdout, r.stdout + r.stderr
    assert "not found" in r.stdout
    assert "install it if you need it" in r.stdout


# --- outcome 3: the tool is present but broken (the regression) ------------


def test_broken_required_tool_fails_the_run(broken_tool: Path) -> None:
    r = _run('require_tool "brokentool" "" brokentool --version', extra_path=broken_tool)
    assert "FAILURES=1" in r.stdout, r.stdout + r.stderr
    assert "failed to run" in r.stderr


def test_broken_optional_tool_fails_the_run(broken_tool: Path) -> None:
    """The regression case. A crashing tool must never be reported as present.

    Optional severity applies to ABSENCE only. `command -v` could not tell
    these apart, which is precisely how a fatally-broken semgrep passed.
    """
    r = _run(
        'optional_tool "brokentool" "optional" brokentool --version',
        extra_path=broken_tool,
    )
    assert "FAILURES=1" in r.stdout, r.stdout + r.stderr
    assert "failed to run" in r.stderr
    assert "not found" not in r.stdout


def test_broken_tool_report_includes_the_underlying_error(broken_tool: Path) -> None:
    """The diagnostic must name the cause, so the operator can act on it."""
    r = _run('require_tool "brokentool" "" brokentool --version', extra_path=broken_tool)
    assert "_cffi_backend" in r.stderr, r.stderr


def test_broken_tool_report_is_truncated_to_one_line(tmp_path: Path) -> None:
    """A crashing tool can emit a wall of text (semgrep printed a Rust panic).

    The report stays a single bounded line so the summary remains readable.
    """
    bindir = tmp_path / "noisy"
    bindir.mkdir()
    tool = bindir / "noisytool"
    tool.write_text(
        '#!/bin/sh\nfor i in $(seq 1 50); do echo "error line $i padding padding" >&2; done\nexit 3\n',
        encoding="utf-8",
    )
    tool.chmod(0o755)

    r = _run('require_tool "noisytool" "" noisytool --version', extra_path=bindir)
    reported = [ln for ln in r.stderr.splitlines() if "failed to run" in ln]
    assert len(reported) == 1, r.stderr
    assert len(reported[0]) < 220, reported[0]
    assert "exit 3" in reported[0]


# --- dev-setup.sh must actually use them ----------------------------------


def test_dev_setup_verifies_through_the_probe_helpers_not_command_v() -> None:
    """The library only helps if the Verifying section routes through it.

    Pins the fix at its call site: no bare `command -v <tool> && ok` pattern
    may return to that section. `command -v` is still legitimate for *branch
    selection* (choosing semgrep's CLI vs module form) — what must not come
    back is `command -v` as the verification itself.
    """
    text = (REPO_ROOT / "scripts" / "dev-setup.sh").read_text(encoding="utf-8")
    verifying = text[text.index('section "Verifying"') : text.index("# --- summary ---")]

    assert "require_tool" in verifying
    assert "optional_tool" in verifying
    # `ok` is emitted by the helpers now; a direct call would mean some tool is
    # still being blessed without being run.
    assert "\n  ok " not in verifying, verifying
