"""Tests for the Stryker.NET adapter's coverage-capture wiring (#1156).

The pure predicate lib.detect_coverage_capture_failure is unit-tested in
test_mutation_adapters_lib.py. These tests armor the production consumer:
stryker_net_run captures the subprocess stdout and emits the #1156 advisory
when the capture-failure signal is present — the exact path #1158 branches on.
"""

from __future__ import annotations

import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from mutation_adapters import stryker_net as sn


def _stub_run(stdout_bytes: bytes):
    def fake_run(_seconds, argv, **_kwargs):
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=stdout_bytes)

    return fake_run


def test_run_emits_advisory_on_capture_failure(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sn, "_changed_cs_file", lambda: "")
    monkeypatch.setattr(
        sn.lib,
        "run_with_timeout",
        _stub_run(
            b"[13:20:25 ERR] It looks like the test coverage capture failed. "
            b"Disable coverage based optimisation.\n"
        ),
    )
    monkeypatch.setattr(sn.lib, "parse_stryker_kills", lambda _rp, _of: None)

    rc = sn.stryker_net_run(tmp_path / "out.json")
    out = capsys.readouterr().out

    assert rc == 0
    assert "#1156" in out
    assert "coverage capture failed" in out.lower()


def test_run_no_advisory_on_clean_output(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sn, "_changed_cs_file", lambda: "")
    monkeypatch.setattr(
        sn.lib,
        "run_with_timeout",
        _stub_run(b"Killed:     42\nThe final mutation score is 84.00 %\n"),
    )
    monkeypatch.setattr(sn.lib, "parse_stryker_kills", lambda _rp, _of: None)

    rc = sn.stryker_net_run(tmp_path / "out.json")
    out = capsys.readouterr().out

    assert rc == 0
    assert "#1156" not in out


# ---------------------------------------------------------------------------
# _is_cs_source() — pure predicate, previously untested
# ---------------------------------------------------------------------------


def test_is_cs_source_true_for_plain_cs() -> None:
    assert sn._is_cs_source("Widget.cs") is True


def test_is_cs_source_false_for_non_cs_extension() -> None:
    assert sn._is_cs_source("Widget.txt") is False


def test_is_cs_source_false_for_test_file() -> None:
    assert sn._is_cs_source("WidgetTest.cs") is False


def test_is_cs_source_false_for_spec_file() -> None:
    assert sn._is_cs_source("WidgetSpec.cs") is False


# ---------------------------------------------------------------------------
# _default_report_path() — default vs env override
# ---------------------------------------------------------------------------


def test_default_report_path_uses_documented_default(monkeypatch) -> None:
    monkeypatch.delenv("STRYKER_NET_REPORT", raising=False)
    assert sn._default_report_path() == sn.Path("StrykerOutput/mutation-report.json")


def test_default_report_path_honors_env_override(monkeypatch) -> None:
    monkeypatch.setenv("STRYKER_NET_REPORT", "custom/report.json")
    assert sn._default_report_path() == sn.Path("custom/report.json")


# ---------------------------------------------------------------------------
# stryker_net_detect() — manifest, dotnet probe, advisory
# ---------------------------------------------------------------------------


def test_detect_true_when_tools_manifest_names_stryker(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "dotnet-tools.json").write_text(
        '{"tools": {"dotnet-stryker": {"version": "4.0.0"}}}'
    )
    monkeypatch.setattr(sn.shutil, "which", lambda _name: None)
    assert sn.stryker_net_detect() is True


def test_detect_true_via_dotnet_stryker_version_probe(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sn.shutil, "which", lambda name: "/usr/bin/dotnet" if name == "dotnet" else None
    )
    calls = {}

    def fake_run(argv, **_kwargs):
        calls["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=0)

    monkeypatch.setattr(sn.subprocess, "run", fake_run)
    assert sn.stryker_net_detect() is True
    assert calls["argv"] == ["dotnet", "stryker", "--version"]


def test_detect_false_advisory_names_setup_and_tool_install(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sn.shutil, "which", lambda _name: None)
    assert sn.stryker_net_detect() is False
    assert (
        "Run /setup to install it, or run: dotnet tool install dotnet-stryker"
        in capsys.readouterr().out
    )


# ---------------------------------------------------------------------------
# _shard_for_file() — shard-config prefix matching
# ---------------------------------------------------------------------------


def test_shard_for_file_returns_none_for_empty_input(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert sn._shard_for_file("") is None


def test_shard_for_file_matches_mutate_prefix(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stryker-config.shard-foo.json").write_text(
        '{"stryker-config": {"mutate": ["src/Foo.Bar/**/*.cs"]}}'
    )
    result = sn._shard_for_file("src/Foo.Bar/Thing.cs")
    assert result == sn.Path("stryker-config.shard-foo.json")


def test_shard_for_file_returns_none_when_prefix_does_not_match(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stryker-config.shard-foo.json").write_text(
        '{"stryker-config": {"mutate": ["src/Foo.Bar/**/*.cs"]}}'
    )
    assert sn._shard_for_file("src/Other/Thing.cs") is None


# ---------------------------------------------------------------------------
# stryker_net_run() — timeout and no-report advisory paths
# ---------------------------------------------------------------------------


def test_run_timeout_writes_empty_list_and_advises(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sn, "_changed_cs_file", lambda: "")

    def fake_run(_seconds, argv, **_kwargs):
        return subprocess.CompletedProcess(args=argv, returncode=124, stdout=b"")

    monkeypatch.setattr(sn.lib, "run_with_timeout", fake_run)

    out_file = tmp_path / "out.json"
    assert sn.stryker_net_run(out_file) == 0
    assert out_file.read_text() == "[]"
    out = capsys.readouterr().out
    assert "Stryker.NET timed out after 600s. For large repos" in out
    assert "Or: ADAPTER_TIMEOUT=<seconds> to " in out


def test_run_nonzero_exit_without_report_writes_empty_and_advises(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sn, "_changed_cs_file", lambda: "")

    def fake_run(_seconds, argv, **_kwargs):
        return subprocess.CompletedProcess(args=argv, returncode=3, stdout=b"")

    monkeypatch.setattr(sn.lib, "run_with_timeout", fake_run)

    out_file = tmp_path / "out.json"
    assert sn.stryker_net_run(out_file) == 0
    assert out_file.read_text() == "[]"
    assert (
        "exited with code 3 and produced no report. Skipping mutation gate."
        in capsys.readouterr().out
    )


# ---------------------------------------------------------------------------
# main() — argument handling + delegation
# ---------------------------------------------------------------------------


def test_main_no_args_returns_2_with_exact_message(capsys) -> None:
    rc = sn.main([])
    assert rc == 2
    assert capsys.readouterr().err == "stryker_net.py: OUTPUT_FILE argument required\n"


def test_main_delegates_first_arg_as_output_path(monkeypatch) -> None:
    captured = {}

    def fake_run(out_file):
        captured["out"] = out_file
        return 0

    monkeypatch.setattr(sn, "stryker_net_run", fake_run)
    rc = sn.main(["out.json", "extra.json"])
    assert rc == 0
    assert captured["out"] == sn.Path("out.json")


# ---------------------------------------------------------------------------
# stryker_net_run() — the dotnet-stryker argv the adapter constructs
# ---------------------------------------------------------------------------


def _capture_argv(monkeypatch):
    captured = {}

    def fake_run(_seconds, argv, **_kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=b"")

    monkeypatch.setattr(sn.lib, "run_with_timeout", fake_run)
    monkeypatch.setattr(sn.lib, "parse_stryker_kills", lambda _rp, _of: None)
    return captured


def test_run_builds_expected_default_stryker_argv(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sn, "_changed_cs_file", lambda: "")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("STRYKER_SINCE_TARGET", raising=False)
    captured = _capture_argv(monkeypatch)

    sn.stryker_net_run(tmp_path / "out.json")
    argv = captured["argv"]

    assert argv[:2] == ["dotnet", "stryker"]
    assert argv[argv.index("--reporter") + 1] == "json"
    assert argv[argv.index("--coverage-analysis") + 1] == "perTest"
    assert argv[argv.index("--mutation-level") + 1] == "Standard"
    assert argv[argv.index("--output") + 1] == "StrykerOutput/gate-shard"


def test_run_uses_matching_shard_config_and_scopes_mutate_to_changed_file(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stryker-config.shard-foo.json").write_text(
        '{"stryker-config": {"mutate": ["src/Foo/**/*.cs"]}}'
    )
    monkeypatch.setattr(sn, "_changed_cs_file", lambda: "src/Foo/Thing.cs")
    captured = _capture_argv(monkeypatch)

    sn.stryker_net_run(tmp_path / "out.json")
    argv = captured["argv"]

    assert argv[argv.index("--config-file") + 1] == "stryker-config.shard-foo.json"
    assert argv[argv.index("--mutate") + 1] == "**/Thing.cs"


def test_run_appends_since_flag_when_env_set_outside_ci(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sn, "_changed_cs_file", lambda: "")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("STRYKER_SINCE_TARGET", "origin/main")
    captured = _capture_argv(monkeypatch)

    sn.stryker_net_run(tmp_path / "out.json")

    assert "--since:origin/main" in captured["argv"]
