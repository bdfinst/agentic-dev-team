"""Tests for the Stryker.NET adapter's coverage-capture wiring (#1156).

The pure predicate lib.detect_coverage_capture_failure is unit-tested in
test_mutation_adapters_lib.py. These tests armor the production consumer:
stryker_net_run captures the subprocess stdout and emits the #1156 advisory
when the capture-failure signal is present — the exact path #1158 branches on.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))

from mutation_adapters import stryker_net as sn  # noqa: E402


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
