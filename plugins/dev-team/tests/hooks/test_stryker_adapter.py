"""Tests for the Stryker (JS/TS) adapter — `mutation_adapters.stryker`.

The module was previously untested. These pin the real behaviour of the pure
helpers (report path, source derivation, configured-timeout parsing), the
stryker_detect probes, the stryker_run argv construction and its timeout /
no-report advisory branches, and main()'s argument handling. Every assertion
checks a specific value, not just a return code.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from mutation_adapters import stryker as st  # noqa: E402


def _capture_argv(monkeypatch, returncode: int = 0):
    captured = {}

    def fake_run(_seconds, argv, **_kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=returncode)

    monkeypatch.setattr(st.lib, "run_with_timeout", fake_run)
    monkeypatch.setattr(st.lib, "parse_stryker_kills", lambda _rp, _of: None)
    return captured


# ---------------------------------------------------------------------------
# _report_path() — default vs env override
# ---------------------------------------------------------------------------


def test_report_path_uses_documented_default(monkeypatch) -> None:
    monkeypatch.delenv("STRYKER_REPORT", raising=False)
    assert st._report_path() == st.Path("reports/mutation/mutation.json")


def test_report_path_honors_env_override(monkeypatch) -> None:
    monkeypatch.setenv("STRYKER_REPORT", "custom/report.json")
    assert st._report_path() == st.Path("custom/report.json")


# ---------------------------------------------------------------------------
# stryker_detect() — bin, package.json, advisory
# ---------------------------------------------------------------------------


def test_detect_true_when_local_bin_present(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    binp = tmp_path / "node_modules" / ".bin"
    binp.mkdir(parents=True)
    (binp / "stryker").write_text("#!/bin/sh\n")
    assert st.stryker_detect() is True


def test_detect_true_when_package_json_declares_core(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "package.json").write_text('{"devDependencies": {"@stryker-mutator/core": "8.0.0"}}')
    assert st.stryker_detect() is True


def test_detect_false_advisory_names_setup_and_core(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert st.stryker_detect() is False
    assert (
        "Run /setup to install it, or add @stryker-mutator/core manually."
        in capsys.readouterr().out
    )


# ---------------------------------------------------------------------------
# derive_source_file() — strip .test./.spec. keeping the extension
# ---------------------------------------------------------------------------


def test_derive_source_file_strips_test_infix_ts() -> None:
    assert st.derive_source_file("calc.test.ts") == "calc.ts"


def test_derive_source_file_strips_spec_infix_js() -> None:
    assert st.derive_source_file("calc.spec.js") == "calc.js"


def test_derive_source_file_preserves_tsx_extension() -> None:
    assert st.derive_source_file("App.test.tsx") == "App.tsx"


def test_derive_source_file_leaves_plain_source_unchanged() -> None:
    assert st.derive_source_file("calc.ts") == "calc.ts"


# ---------------------------------------------------------------------------
# _read_configured_timeout_ms() — .strykerrc.json + config-file grep
# ---------------------------------------------------------------------------


def test_configured_timeout_reads_timeoutms_from_rc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".strykerrc.json").write_text('{"timeoutMS": 8000}')
    assert st._read_configured_timeout_ms() == 8000


def test_configured_timeout_falls_back_to_timeout_key(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".strykerrc.json").write_text('{"timeout": 4500}')
    assert st._read_configured_timeout_ms() == 4500


def test_configured_timeout_none_when_rc_has_no_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".strykerrc.json").write_text('{"concurrency": 4}')
    assert st._read_configured_timeout_ms() is None


def test_configured_timeout_greps_config_js(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stryker.config.js").write_text("module.exports = { timeoutMS: 6000 };\n")
    assert st._read_configured_timeout_ms() == 6000


def test_configured_timeout_none_when_nothing_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert st._read_configured_timeout_ms() is None


# ---------------------------------------------------------------------------
# stryker_run() — argv construction
# ---------------------------------------------------------------------------


def test_run_builds_expected_default_argv(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADAPTER_SOURCE_FILE", raising=False)
    captured = _capture_argv(monkeypatch)

    st.stryker_run(tmp_path / "out.json")
    argv = captured["argv"]

    assert argv[:3] == ["npx", "stryker", "run"]
    assert argv[argv.index("--reporters") + 1] == "json"
    assert argv[argv.index("--coverageAnalysis") + 1] == "perTest"
    assert "--mutate" not in argv


def test_run_scopes_mutate_to_source_file_env(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADAPTER_SOURCE_FILE", "src/calc.ts")
    captured = _capture_argv(monkeypatch)

    st.stryker_run(tmp_path / "out.json")
    argv = captured["argv"]

    assert argv[argv.index("--mutate") + 1] == "src/calc.ts"


# ---------------------------------------------------------------------------
# stryker_run() — timeout and no-report advisory paths
# ---------------------------------------------------------------------------


def test_run_timeout_writes_empty_list_and_advises_config_hint(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADAPTER_SOURCE_FILE", raising=False)
    _capture_argv(monkeypatch, returncode=124)

    out_file = tmp_path / "out.json"
    assert st.stryker_run(out_file) == 0
    assert out_file.read_text() == "[]"
    out = capsys.readouterr().out
    assert "Stryker timed out after 300s." in out
    assert "Add 'timeoutMS: <ms>' to stryker.config.js to cap per-mutant runs." in out
    assert "Or: MUTATION_GATE_TIMEOUT=<seconds> to extend the outer limit." in out


def test_run_timeout_omits_config_hint_when_timeout_configured(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADAPTER_SOURCE_FILE", raising=False)
    (tmp_path / ".strykerrc.json").write_text('{"timeoutMS": 5000}')
    _capture_argv(monkeypatch, returncode=124)

    out_file = tmp_path / "out.json"
    assert st.stryker_run(out_file) == 0
    out = capsys.readouterr().out
    assert "Stryker timed out after 300s. Or: MUTATION_GATE_TIMEOUT" in out
    assert "Add 'timeoutMS:" not in out


def test_run_nonzero_exit_without_report_writes_empty_and_advises(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADAPTER_SOURCE_FILE", raising=False)
    _capture_argv(monkeypatch, returncode=7)

    out_file = tmp_path / "out.json"
    assert st.stryker_run(out_file) == 0
    assert out_file.read_text() == "[]"
    assert (
        "exited with code 7 and produced no report. Skipping mutation gate."
        in capsys.readouterr().out
    )


# ---------------------------------------------------------------------------
# main() — argument handling + delegation
# ---------------------------------------------------------------------------


def test_main_no_args_returns_2_with_exact_message(capsys) -> None:
    rc = st.main([])
    assert rc == 2
    assert capsys.readouterr().err == "stryker.py: OUTPUT_FILE argument required\n"


def test_main_delegates_first_arg_as_output_path(monkeypatch) -> None:
    captured = {}

    def fake_run(out_file):
        captured["out"] = out_file
        return 0

    monkeypatch.setattr(st, "stryker_run", fake_run)
    rc = st.main(["out.json", "extra.json"])
    assert rc == 0
    assert captured["out"] == st.Path("out.json")
