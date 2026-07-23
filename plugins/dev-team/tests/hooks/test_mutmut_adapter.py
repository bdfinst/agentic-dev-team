"""Tests for the mutmut (Python) adapter's real-CLI contract.

The shipped adapter shipped with two latent bugs, confirmed by running the
real `mutmut` 2.x CLI against this repo's own code while dogfooding the
mutation-testing pipeline (issue tracking: mutmut/python-setup epic):

1. `mutmut_detect()`'s fallback probe used `python3 -m mutmut --version` — a
   flag that does not exist on the real CLI (it is a `version` subcommand)
   and always exits nonzero, so the fallback always read as "not installed".
2. `mutmut_run()` treated any exit code `>= 2` as a tool error to skip. The
   real CLI's exit code is a bitmask (1=fatal error, 2=survived, 4=timeout,
   8=slow); a run with survivors — the common, expected case — legitimately
   returns 2 (or higher combined with other bits), so the gate silently
   discarded every real survivor list. It also read results via
   `mutmut results --json`, a flag the CLI does not support at all — the
   call always failed and fell back to an empty list regardless of the real
   exit code.

These tests pin the fixed behavior against the real CLI's documented/
observed contract (exit-code bitmask, `mutmut junitxml` output shape).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from mutation_adapters import mutmut as mm  # noqa: E402

_JUNIT_ALL_KILLED = """<?xml version="1.0" ?>
<testsuites disabled="0" errors="0" failures="0" tests="2" time="0.0">
\t<testsuite disabled="0" errors="0" failures="0" name="mutmut" tests="2" time="0">
\t\t<testcase name="Mutant #1" file="src/calc.py" line="5">
\t\t\t<system-out>x = 1</system-out>
\t\t</testcase>
\t\t<testcase name="Mutant #2" file="src/calc.py" line="6">
\t\t\t<system-out>y = 2</system-out>
\t\t</testcase>
\t</testsuite>
</testsuites>
"""

_JUNIT_ONE_SURVIVOR = """<?xml version="1.0" ?>
<testsuites disabled="0" errors="0" failures="1" tests="2" time="0.0">
\t<testsuite disabled="0" errors="0" failures="1" name="mutmut" tests="2" time="0">
\t\t<testcase name="Mutant #1" file="src/calc.py" line="5">
\t\t\t<system-out>x = 1</system-out>
\t\t</testcase>
\t\t<testcase name="Mutant #2" file="src/calc.py" line="12">
\t\t\t<failure type="failure" message="bad_survived">--- diff ---</failure>
\t\t\t<system-out>y = 2</system-out>
\t\t</testcase>
\t</testsuite>
</testsuites>
"""


def _stub_run_with_timeout(returncode: int, stderr: str = ""):
    def fake_run(_seconds, argv, **_kwargs):
        return subprocess.CompletedProcess(args=argv, returncode=returncode, stderr=stderr)

    return fake_run


def _stub_subprocess_run(stdout: str):
    def fake_run(_argv, **_kwargs):
        return subprocess.CompletedProcess(args=_argv, returncode=0, stdout=stdout)

    return fake_run


# ---------------------------------------------------------------------------
# mutmut_detect() — the `version` subcommand fallback (not `--version`)
# ---------------------------------------------------------------------------


def test_detect_true_when_console_script_on_path(monkeypatch) -> None:
    monkeypatch.setattr(mm.shutil, "which", lambda _name: "/usr/local/bin/mutmut")
    assert mm.mutmut_detect() is True


def test_detect_true_via_version_subcommand_fallback(monkeypatch) -> None:
    monkeypatch.setattr(mm.shutil, "which", lambda _name: None)
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0)

    monkeypatch.setattr(mm.subprocess, "run", fake_run)
    assert mm.mutmut_detect() is True
    assert calls == [["python3", "-m", "mutmut", "version"]]


def test_detect_false_and_advisory_when_absent(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mm.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        mm.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(args=argv, returncode=2),
    )
    assert mm.mutmut_detect() is False
    assert "not installed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# mutmut_run() — exit-code bitmask + junitxml parsing
# ---------------------------------------------------------------------------


def test_run_all_killed_writes_empty_zero_kills(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(0))
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run(_JUNIT_ALL_KILLED))

    out_file = tmp_path / "zero-kills.json"
    rc = mm.mutmut_run(out_file)

    assert rc == 0
    assert out_file.read_text() == "[]"


def test_run_with_survivors_bit_still_parses_results(tmp_path, monkeypatch) -> None:
    """Exit code 2 (survived bit) is the expected, common outcome — not an
    error — and must still yield the survivor from junitxml."""
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(2))
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run(_JUNIT_ONE_SURVIVOR))

    out_file = tmp_path / "zero-kills.json"
    rc = mm.mutmut_run(out_file)

    assert rc == 0
    import json

    zero_kills = json.loads(out_file.read_text())
    assert zero_kills == [
        {"name": "mutant_Mutant #2", "file": "src/calc.py", "line": 12, "covered": 0}
    ]


def test_run_survived_plus_slow_bits_still_parses_results(tmp_path, monkeypatch) -> None:
    """Real observed exit code: 10 = survived (2) | slow (8) — no fatal bit."""
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(10))
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run(_JUNIT_ONE_SURVIVOR))

    out_file = tmp_path / "zero-kills.json"
    rc = mm.mutmut_run(out_file)

    assert rc == 0
    import json

    assert len(json.loads(out_file.read_text())) == 1


def test_run_fatal_error_bit_skips_gate(tmp_path, monkeypatch, capsys) -> None:
    """Exit code 1 (fatal error only) must skip — the baseline run itself
    failed, so there is nothing valid to parse."""
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(1))

    called = []

    def fake_run(argv, **_kwargs):
        called.append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")

    monkeypatch.setattr(mm.subprocess, "run", fake_run)

    out_file = tmp_path / "zero-kills.json"
    rc = mm.mutmut_run(out_file)

    assert rc == 0
    assert out_file.read_text() == "[]"
    assert not called, "must not attempt to read junitxml after a fatal error"
    assert "MUTATION GATE ADVISORY" in capsys.readouterr().out


def test_run_timeout_skips_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(124))

    out_file = tmp_path / "zero-kills.json"
    rc = mm.mutmut_run(out_file)

    assert rc == 0
    assert out_file.read_text() == "[]"


def test_run_malformed_junitxml_yields_empty_list_not_a_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(2))
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run("not xml at all"))

    out_file = tmp_path / "zero-kills.json"
    rc = mm.mutmut_run(out_file)

    assert rc == 0
    assert out_file.read_text() == "[]"


# ---------------------------------------------------------------------------
# _is_python_source() — pure predicate, previously wholly untested
# ---------------------------------------------------------------------------


def test_is_python_source_true_for_plain_py() -> None:
    assert mm._is_python_source("calculator.py") is True


def test_is_python_source_false_for_non_py_extension() -> None:
    assert mm._is_python_source("calculator.txt") is False


def test_is_python_source_false_for_test_prefixed_file() -> None:
    assert mm._is_python_source("test_calculator.py") is False


def test_is_python_source_false_for_underscore_test_suffix() -> None:
    assert mm._is_python_source("calculator_test.py") is False


def test_is_python_source_false_for_nested_test_path() -> None:
    assert mm._is_python_source("pkg/test_calculator.py") is False


# ---------------------------------------------------------------------------
# _derive_python_source() — prefix/suffix stripping + dir search order
# ---------------------------------------------------------------------------


def test_derive_python_source_strips_test_prefix_and_finds_src(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calculator.py").write_text("x = 1\n")
    assert mm._derive_python_source("test_calculator.py") == "src/calculator.py"


def test_derive_python_source_strips_test_suffix_and_finds_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "widget.py").write_text("x = 1\n")
    assert mm._derive_python_source("widget_test.py") == "widget.py"


def test_derive_python_source_checks_lib_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "gadget.py").write_text("x = 1\n")
    assert mm._derive_python_source("test_gadget.py") == "lib/gadget.py"


def test_derive_python_source_falls_back_to_input_when_no_source(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert mm._derive_python_source("test_absent.py") == "test_absent.py"


# ---------------------------------------------------------------------------
# _mutmut_argv() — console-script vs module-form fallback
# ---------------------------------------------------------------------------


def test_mutmut_argv_uses_console_script_when_on_path(monkeypatch) -> None:
    monkeypatch.setattr(
        mm.shutil, "which", lambda name: "/usr/local/bin/mutmut" if name == "mutmut" else None
    )
    assert mm._mutmut_argv() == ["mutmut"]


def test_mutmut_argv_falls_back_to_python_module_form(monkeypatch) -> None:
    monkeypatch.setattr(mm.shutil, "which", lambda _name: None)
    assert mm._mutmut_argv() == ["python3", "-m", "mutmut"]


# ---------------------------------------------------------------------------
# mutmut_detect() — exact program name + full advisory text
# ---------------------------------------------------------------------------


def test_detect_probes_the_exact_program_name(monkeypatch) -> None:
    monkeypatch.setattr(
        mm.shutil, "which", lambda name: "/bin/mutmut" if name == "mutmut" else None
    )
    monkeypatch.setattr(
        mm.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(args=argv, returncode=2),
    )
    assert mm.mutmut_detect() is True


def test_detect_advisory_names_setup_and_pip_install(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mm.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        mm.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(args=argv, returncode=2),
    )
    assert mm.mutmut_detect() is False
    out = capsys.readouterr().out
    assert "Run /setup to install it, or: pip install mutmut" in out


# ---------------------------------------------------------------------------
# mutmut_run() — advisory text on the timeout and fatal-error paths
# ---------------------------------------------------------------------------


def test_run_timeout_advisory_names_seconds_and_env_override(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(124))
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run(""))

    out_file = tmp_path / "z.json"
    assert mm.mutmut_run(out_file) == 0
    out = capsys.readouterr().out
    assert "120s. Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the limit." in out


def test_run_timeout_no_source_advisory_names_missing_scope(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(124))
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run(""))

    out_file = tmp_path / "z.json"
    assert mm.mutmut_run(out_file) == 0
    assert "120s. No source file detected" in capsys.readouterr().out


def test_run_fatal_error_advisory_names_exit_code_and_skip(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(mm.lib, "run_with_timeout", _stub_run_with_timeout(1))
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run(""))

    out_file = tmp_path / "z.json"
    assert mm.mutmut_run(out_file) == 0
    assert "exited with code 1. Skipping mutation gate." in capsys.readouterr().out


def test_run_fatal_error_names_python_314_pickle_crash_when_detected(
    tmp_path, monkeypatch, capsys
) -> None:
    """mutmut<3 crashes with `TypeError: cannot pickle 'itertools.count'
    object` on Python 3.13+ (a parso/pony-ORM deepcopy incompatibility,
    #1359) — a real, reproducible fatal error, not a generic one. The
    advisory should name the known cause and the fix (install mutmut into
    a <=3.12 venv) rather than leaving the operator to rediscover it."""
    monkeypatch.setattr(mm, "_changed_python_source", lambda: "src/calc.py")
    monkeypatch.setattr(mm, "_mutmut_argv", lambda: ["mutmut"])
    monkeypatch.setattr(
        mm.lib,
        "run_with_timeout",
        _stub_run_with_timeout(
            1, stderr="TypeError: cannot pickle 'itertools.count' object"
        ),
    )
    monkeypatch.setattr(mm.subprocess, "run", _stub_subprocess_run(""))

    out_file = tmp_path / "z.json"
    assert mm.mutmut_run(out_file) == 0
    out = capsys.readouterr().out
    assert "exited with code 1. Skipping mutation gate." in out
    assert "Python 3.13+" in out
    assert "<=3.12" in out


# ---------------------------------------------------------------------------
# main() — argument handling + delegation to mutmut_run
# ---------------------------------------------------------------------------


def test_main_no_args_returns_2_with_exact_message(capsys) -> None:
    rc = mm.main([])
    assert rc == 2
    assert capsys.readouterr().err == "mutmut.py: OUTPUT_FILE argument required\n"


def test_main_delegates_first_arg_as_output_path(monkeypatch) -> None:
    captured = {}

    def fake_run(out_file):
        captured["out"] = out_file
        return 0

    monkeypatch.setattr(mm, "mutmut_run", fake_run)
    rc = mm.main(["result.json", "extra.json"])
    assert rc == 0
    assert captured["out"] == mm.Path("result.json")
