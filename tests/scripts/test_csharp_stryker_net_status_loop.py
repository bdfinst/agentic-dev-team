"""Pytest tests for csharp_stryker_net_status_loop.py — the shipped
Stryker.NET status + red-flag inspection loop (#558, #571, #572).

Reuses the existing fixture logs under tests/fixtures/stryker-net-logs/ that
the bats suite already exercises — same schema, same behavior. Each red-flag
detector gets a positive and a negative test; the parser-drift catch-all
gets a counter-reset test that closes #571 at the source (the Python port
doesn't fork subprocesses in setup, so no MSYS hang).

Contract preserved: 14 pytest tests replace and expand on the 14 bats tests
in mutation_testing_status_loop_tests.bats.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

LOOP_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(LOOP_DIR))

import csharp_stryker_net_status_loop as loop  # noqa: E402

FIXTURES = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "stryker-net-logs"
)


# =============================================================================
# PID helpers — no fork-in-setup hangs on any platform (closes #571)
# =============================================================================
@pytest.fixture
def alive_pid() -> int:
    """A PID we can be sure is alive — the pytest process itself."""
    return os.getpid()


@pytest.fixture
def dead_pid() -> int:
    """A PID we can be sure is NOT alive. Uses a large integer well outside
    any reasonable PID range instead of the bash version's forked child +
    wait (which hangs on MSYS bash — see #571).
    """
    # Verify the PID really is dead. If somehow this exact number is in use
    # on the test host, use another one.
    candidate = 99999999
    if loop._pid_is_alive(candidate):
        candidate = 99999998
    assert not loop._pid_is_alive(candidate), (
        "Test-invariant PID unexpectedly alive; pick a different one"
    )
    return candidate


@pytest.fixture
def state_dir(tmp_path) -> Path:
    """Per-test drift-counter state dir so counter runs don't leak."""
    d = tmp_path / "loop-state"
    d.mkdir()
    return d


# =============================================================================
# Log parsers — pure functions
# =============================================================================
class TestParsers:
    def test_dots_count_on_healthy_log(self):
        # Healthy fixture has one line of dots after 'Testing mutants:'.
        n = loop.parse_dots_count(FIXTURES / "healthy-dots.log")
        assert n > 0

    def test_dots_count_on_log_without_marker_returns_zero(self, tmp_path):
        f = tmp_path / "no-marker.log"
        f.write_text("nothing here\n")
        assert loop.parse_dots_count(f) == 0

    def test_dots_count_on_missing_file_returns_zero(self, tmp_path):
        assert loop.parse_dots_count(tmp_path / "does-not-exist.log") == 0

    def test_summary_count_extracts_last_matching_line(self, tmp_path):
        f = tmp_path / "log.log"
        f.write_text("Killed:  10\nSurvived: 5\nTimeout: 0\nKilled: 42\n")
        assert loop.parse_summary_count(f, "Killed") == 42
        assert loop.parse_summary_count(f, "Survived") == 5

    def test_summary_count_returns_none_when_absent(self, tmp_path):
        f = tmp_path / "log.log"
        f.write_text("no summary here\n")
        assert loop.parse_summary_count(f, "Killed") is None

    def test_completion_marker_present(self):
        # The healthy fixture ends with a "The final mutation score" line.
        assert loop.log_has_completion_marker(FIXTURES / "healthy-dots.log")

    def test_completion_marker_absent(self):
        assert not loop.log_has_completion_marker(
            FIXTURES / "truncated-dead-process.log"
        )


# =============================================================================
# emit_status_line — one-record output shape
# =============================================================================
class TestEmitStatusLine:
    def test_healthy_log_emits_expected_fields(self):
        line = loop.emit_status_line(FIXTURES / "healthy-dots.log")
        # Contains each documented field.
        for field in ("tested=", "killed=", "survived=", "timeout=", "elapsed="):
            assert field in line

    def test_missing_log_emits_zeroed_record(self, tmp_path):
        line = loop.emit_status_line(tmp_path / "no-file.log")
        assert "tested=0" in line
        assert "killed=0" in line


# =============================================================================
# check_red_flags — each of the five detectors
# =============================================================================
class TestRedFlagKilledSurvived:
    def test_fires_when_killed_zero_and_survived_positive(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "mutation-switch-broken.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        killed_flag = [f for f in flags if "mutation-switch not observing" in f]
        assert len(killed_flag) == 1
        assert "#554" in killed_flag[0]

    def test_silent_on_healthy_log(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "healthy-dots.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        assert not any("mutation-switch" in f for f in flags)


class TestRedFlagCompileError:
    def test_fires_when_count_strictly_over_threshold(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "compile-error-above.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        ce = [f for f in flags if "CompileError count" in f]
        assert len(ce) == 1
        # Names the count and threshold.
        assert " over threshold 25" in ce[0]

    def test_silent_when_count_equal_to_threshold(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "compile-error-at.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        assert not any("CompileError count" in f for f in flags)


class TestRedFlagSolutionPath:
    def test_fires_on_unexpected_targetpath(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "solution-path-trap.log",
            threshold=25,
            stryker_pid=alive_pid,
            expected_target="expected-project.dll",
            state_dir=state_dir,
        )
        sp = [f for f in flags if "SolutionPath trap" in f]
        assert len(sp) == 1
        assert "#557" in sp[0]

    def test_silent_when_no_expected_target_set(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "solution-path-trap.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        assert not any("SolutionPath trap" in f for f in flags)


class TestRedFlagDeadStryker:
    def test_fires_when_pid_dead_and_no_completion_marker(self, state_dir, dead_pid):
        flags = loop.check_red_flags(
            FIXTURES / "truncated-dead-process.log",
            threshold=25,
            stryker_pid=dead_pid,
            state_dir=state_dir,
        )
        died = [f for f in flags if "Stryker process died" in f]
        assert len(died) == 1
        assert "#558" in died[0]

    def test_silent_when_pid_dead_but_completion_marker_present(
        self, state_dir, dead_pid
    ):
        """A completed successful run leaves the PID reaped — normal, not a
        red flag. Healthy log ends with the completion marker."""
        flags = loop.check_red_flags(
            FIXTURES / "healthy-dots.log",
            threshold=25,
            stryker_pid=dead_pid,
            state_dir=state_dir,
        )
        assert not any("Stryker process died" in f for f in flags)

    def test_silent_when_pid_alive_even_without_completion_marker(
        self, state_dir, alive_pid
    ):
        flags = loop.check_red_flags(
            FIXTURES / "truncated-dead-process.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        assert not any("Stryker process died" in f for f in flags)


class TestRedFlagParserDrift:
    def test_first_and_second_unrecognized_ticks_do_not_fire(
        self, state_dir, alive_pid
    ):
        for _ in range(2):
            flags = loop.check_red_flags(
                FIXTURES / "unrecognized.log",
                threshold=25,
                stryker_pid=alive_pid,
                state_dir=state_dir,
                drift_threshold=3,
            )
            assert not any("parser drift" in f for f in flags)

    def test_third_unrecognized_tick_fires_parser_drift(self, state_dir, alive_pid):
        # Prime the counter to 2.
        loop.check_red_flags(
            FIXTURES / "unrecognized.log",
            25,
            alive_pid,
            state_dir=state_dir,
            drift_threshold=3,
        )
        loop.check_red_flags(
            FIXTURES / "unrecognized.log",
            25,
            alive_pid,
            state_dir=state_dir,
            drift_threshold=3,
        )
        # 3rd tick — drift fires.
        flags = loop.check_red_flags(
            FIXTURES / "unrecognized.log",
            25,
            alive_pid,
            state_dir=state_dir,
            drift_threshold=3,
        )
        drift = [f for f in flags if "parser drift" in f]
        assert len(drift) == 1
        assert "#558" in drift[0]

    def test_recognized_tick_resets_the_counter(self, state_dir, alive_pid):
        # Two unrecognized, then one recognized — counter resets.
        loop.check_red_flags(
            FIXTURES / "unrecognized.log",
            25,
            alive_pid,
            state_dir=state_dir,
            drift_threshold=3,
        )
        loop.check_red_flags(
            FIXTURES / "unrecognized.log",
            25,
            alive_pid,
            state_dir=state_dir,
            drift_threshold=3,
        )
        # Recognized tick.
        loop.check_red_flags(
            FIXTURES / "healthy-dots.log",
            25,
            alive_pid,
            state_dir=state_dir,
            drift_threshold=3,
        )
        # Now two more unrecognized — should NOT fire (counter was reset).
        for _ in range(2):
            flags = loop.check_red_flags(
                FIXTURES / "unrecognized.log",
                25,
                alive_pid,
                state_dir=state_dir,
                drift_threshold=3,
            )
            assert not any("parser drift" in f for f in flags)


# =============================================================================
# CLI — one-shot mode
# =============================================================================
class TestCLI:
    def test_one_shot_mode_emits_status_and_exits(self, tmp_path):
        """interval=0 → one tick then exit. Verifies the CLI path works
        without spawning a loop that could hang."""
        script = LOOP_DIR / "csharp_stryker_net_status_loop.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                str(FIXTURES / "healthy-dots.log"),
                "0",
                "25",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "tested=" in result.stdout

    def test_one_shot_emits_red_flag_on_broken_log(self):
        script = LOOP_DIR / "csharp_stryker_net_status_loop.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                str(FIXTURES / "mutation-switch-broken.log"),
                "0",
                "25",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "[RED-FLAG]" in result.stdout
        assert "#554" in result.stdout


# =============================================================================
# Red flag 6 — coverage capture failure (#1156)
# =============================================================================
class TestRedFlagCoverageCapture:
    def test_fires_on_coverage_capture_failure(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "coverage-capture-failed.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        capture = [f for f in flags if "coverage capture failed" in f]
        assert len(capture) == 1
        assert "#1156" in capture[0]

    def test_silent_on_healthy_log(self, state_dir, alive_pid):
        flags = loop.check_red_flags(
            FIXTURES / "healthy-dots.log",
            threshold=25,
            stryker_pid=alive_pid,
            state_dir=state_dir,
        )
        assert not any("coverage capture failed" in f for f in flags)

    def test_helper_matches_either_half_case_insensitively(self, tmp_path):
        first = tmp_path / "first.log"
        first.write_text("[13:20:25 ERR] it looks like the TEST COVERAGE CAPTURE FAILED.\n")
        second = tmp_path / "second.log"
        second.write_text("[13:20:25 ERR] Disable Coverage Based Optimisation.\n")
        clean = tmp_path / "clean.log"
        clean.write_text("Killed:     42\nThe final mutation score is 84.00 %\n")
        assert loop.log_has_coverage_capture_failure(first) is True
        assert loop.log_has_coverage_capture_failure(second) is True
        assert loop.log_has_coverage_capture_failure(clean) is False

    def test_missing_file_is_false(self, tmp_path):
        assert loop.log_has_coverage_capture_failure(tmp_path / "nope.log") is False


def test_coverage_capture_regex_matches_adapter_copy():
    """The signal regex is duplicated across the status loop (skills/) and the
    adapter lib (hooks/) because they have no shared import root. This armors
    the 'kept byte-identical' comment so a drift or spelling 'fix' in one copy
    cannot pass unnoticed. See #1156."""
    hooks_dir = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "hooks"
    sys.path.insert(0, str(hooks_dir))
    from mutation_adapters import lib  # noqa: E402

    assert (
        loop._COVERAGE_CAPTURE_FAILURE_RE.pattern
        == lib._COVERAGE_CAPTURE_FAILURE_RE.pattern
    )
    assert (
        loop._COVERAGE_CAPTURE_FAILURE_RE.flags == lib._COVERAGE_CAPTURE_FAILURE_RE.flags
    )
