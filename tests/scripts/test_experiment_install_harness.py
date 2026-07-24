"""Tests for scripts/experiment_install_harness.py (#1098, epic #1097).

Covers: --dry-run command construction for both arms, manifest schema and
content with mocked subprocess execution, and the verification-probe logic
against temp dirs (marker present / absent / inconclusive).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPT_PY = _REPO_ROOT / "scripts" / "experiment_install_harness.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "experiment_install_harness", _SCRIPT_PY
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _load_harness()


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


def test_control_commands_use_published_marketplace_and_user_scope() -> None:
    cmds = H.build_install_commands(
        H.CONTROL, "bdfinst/agentic-dev-team", "dev-team@bfinster"
    )
    assert cmds == [
        ["claude", "plugin", "marketplace", "add", "bdfinst/agentic-dev-team"],
        ["claude", "plugin", "install", "dev-team@bfinster"],
    ]


def test_treatment_commands_use_checkout_path_and_project_scope() -> None:
    cmds = H.build_install_commands(
        H.TREATMENT, "/tmp/experiment-checkout", "dev-team@bfinster"
    )
    assert cmds == [
        ["claude", "plugin", "marketplace", "add", "/tmp/experiment-checkout"],
        ["claude", "plugin", "install", "--scope", "project", "dev-team@bfinster"],
    ]


def test_unknown_arm_rejected() -> None:
    with pytest.raises(ValueError):
        H.build_install_commands("placebo", "x", "dev-team@bfinster")


# ---------------------------------------------------------------------------
# --dry-run end to end (subprocess; claude CLI not required)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path):
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
    )


def test_dry_run_prints_both_arms_and_writes_manifest(tmp_path: Path) -> None:
    checkout = tmp_path / "branch-checkout"
    checkout.mkdir()
    r = _run_cli(
        "--dry-run",
        "--workdir", str(tmp_path / "work"),
        "--experiment-checkout", str(checkout),
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "claude plugin marketplace add bdfinst/agentic-dev-team" in out
    assert "claude plugin install dev-team@bfinster" in out
    assert "claude plugin marketplace add %s" % checkout.resolve() in out
    assert "claude plugin install --scope project dev-team@bfinster" in out

    manifest = json.loads(
        (tmp_path / "work" / "experiment-manifest.json").read_text()
    )
    assert manifest["dry_run"] is True
    assert set(manifest["arms"]) == {"control", "treatment"}
    for arm in manifest["arms"].values():
        assert arm["executed"] is False
        assert arm["installed_at"] is None
        assert arm["probe"]["present"] is None
        assert arm["probe"]["passed"] is None


def test_dry_run_control_only_needs_no_checkout(tmp_path: Path) -> None:
    r = _run_cli(
        "--dry-run", "--control-only", "--workdir", str(tmp_path / "w"),
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stderr
    manifest = json.loads((tmp_path / "w" / "experiment-manifest.json").read_text())
    assert set(manifest["arms"]) == {"control"}
    assert manifest["arms"]["control"]["arm"] == "B"
    assert manifest["arms"]["control"]["install_scope"] == "user"


def test_treatment_requires_checkout(tmp_path: Path) -> None:
    r = _run_cli("--dry-run", "--treatment-only", cwd=tmp_path)
    assert r.returncode != 0
    assert "--experiment-checkout" in r.stderr


def test_missing_claude_cli_is_actionable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(H.shutil, "which", lambda _name: None)
    checkout = tmp_path / "co"
    checkout.mkdir()
    code = H.main(
        ["--workdir", str(tmp_path / "w"), "--experiment-checkout", str(checkout)]
    )
    assert code == 3


# ---------------------------------------------------------------------------
# Manifest schema/content with mocked subprocess
# ---------------------------------------------------------------------------


def _fake_checkout(tmp_path: Path, version: str = "10.99.0") -> Path:
    checkout = tmp_path / "branch-checkout"
    plug = checkout / "plugins" / "dev-team" / ".claude-plugin"
    plug.mkdir(parents=True)
    (plug / "plugin.json").write_text(json.dumps({"version": version}))
    return checkout


def _installed_plugin(root: Path, with_marker: bool) -> Path:
    d = root / "installed-plugin"
    (d / ".claude-plugin").mkdir(parents=True)
    (d / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "10.11.0"})
    )
    if with_marker:
        (d / "knowledge").mkdir()
        (d / "knowledge" / "fanout-economics.md").write_text("# Fan-out economics\n")
    return d


def test_full_run_manifest_with_mocked_subprocess(tmp_path: Path, monkeypatch) -> None:
    checkout = _fake_checkout(tmp_path)
    control_plug = _installed_plugin(tmp_path / "ctl", with_marker=False)
    treat_plug = _installed_plugin(tmp_path / "trt", with_marker=True)

    calls = []

    def fake_run(cmd, cwd, config_dir):
        calls.append((list(cmd), Path(cwd), Path(config_dir)))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(H, "run_command", fake_run)
    monkeypatch.setattr(H, "git_head_sha", lambda _p: "deadbeef" * 5)
    monkeypatch.setattr(H.shutil, "which", lambda _n: "/usr/bin/claude")

    manifest_path = tmp_path / "m.json"
    code = H.main(
        [
            "--workdir", str(tmp_path / "work"),
            "--experiment-checkout", str(checkout),
            "--control-plugin-dir", str(control_plug),
            "--treatment-plugin-dir", str(treat_plug),
            "--manifest", str(manifest_path),
        ]
    )
    assert code == 0
    assert len(calls) == 4  # two commands per arm

    doc = json.loads(manifest_path.read_text())
    assert doc["schema_version"] == H.SCHEMA_VERSION
    assert doc["dry_run"] is False

    control = doc["arms"]["control"]
    assert control["arm"] == "B"
    assert control["install_source"] == "bdfinst/agentic-dev-team"
    assert control["install_scope"] == "user"
    assert control["plugin_version"] == "10.11.0"
    assert control["release_tag"] == "dev-team-v10.11.0"
    assert control["probe"] == {
        "marker": "knowledge/fanout-economics.md",
        "marker_string": None,
        "expected_present": False,
        "present": False,
        "passed": True,
    }
    assert control["band_model_map"]["recorded_at_runtime"] is True
    assert control["band_model_map"]["bands"] is None
    assert control["installed_at"] is not None

    treatment = doc["arms"]["treatment"]
    assert treatment["arm"] == "C"
    assert treatment["install_source"] == str(checkout.resolve())
    assert treatment["install_scope"] == "project"
    assert treatment["resolved_sha"] == "deadbeef" * 5
    assert treatment["release_tag"] is None
    assert treatment["probe"]["expected_present"] is True
    assert treatment["probe"]["present"] is True
    assert treatment["probe"]["passed"] is True

    # Isolation: each arm ran in its own project dir with its own config dir.
    control_cfgs = {c[2] for c in calls[:2]}
    treatment_cfgs = {c[2] for c in calls[2:]}
    assert control_cfgs != treatment_cfgs


def test_probe_failure_sets_exit_code_2(tmp_path: Path, monkeypatch) -> None:
    """Treatment arm whose installed plugin LACKS the marker → wrong build."""
    checkout = _fake_checkout(tmp_path)
    stale_plug = _installed_plugin(tmp_path / "trt", with_marker=False)

    monkeypatch.setattr(
        H, "run_command",
        lambda cmd, cwd, config_dir: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    monkeypatch.setattr(H, "git_head_sha", lambda _p: "abc123")
    monkeypatch.setattr(H.shutil, "which", lambda _n: "/usr/bin/claude")

    code = H.main(
        [
            "--treatment-only",
            "--workdir", str(tmp_path / "work"),
            "--experiment-checkout", str(checkout),
            "--treatment-plugin-dir", str(stale_plug),
        ]
    )
    assert code == 2


def test_install_failure_propagates_exit_code_1(tmp_path: Path, monkeypatch) -> None:
    checkout = _fake_checkout(tmp_path)

    def failing_run(cmd, cwd, config_dir):
        raise subprocess.CalledProcessError(42, cmd, output="", stderr="boom")

    monkeypatch.setattr(H, "run_command", failing_run)
    monkeypatch.setattr(H, "git_head_sha", lambda _p: None)
    monkeypatch.setattr(H.shutil, "which", lambda _n: "/usr/bin/claude")

    code = H.main(
        [
            "--treatment-only",
            "--workdir", str(tmp_path / "work"),
            "--experiment-checkout", str(checkout),
            "--treatment-plugin-dir", str(_installed_plugin(tmp_path, True)),
        ]
    )
    assert code >= 1


# ---------------------------------------------------------------------------
# Probe logic against temp dirs
# ---------------------------------------------------------------------------


def test_probe_marker_present(tmp_path: Path) -> None:
    d = _installed_plugin(tmp_path, with_marker=True)
    assert H.probe_marker(d, "knowledge/fanout-economics.md") is True


def test_probe_marker_absent(tmp_path: Path) -> None:
    d = _installed_plugin(tmp_path, with_marker=False)
    assert H.probe_marker(d, "knowledge/fanout-economics.md") is False


def test_probe_marker_string_match_and_mismatch(tmp_path: Path) -> None:
    d = _installed_plugin(tmp_path, with_marker=True)
    assert H.probe_marker(d, "knowledge/fanout-economics.md", "Fan-out") is True
    assert H.probe_marker(d, "knowledge/fanout-economics.md", "absent-str") is False


def test_probe_inconclusive_without_plugin_dir() -> None:
    assert H.probe_marker(None, "knowledge/fanout-economics.md") is None


def test_evaluate_probe_semantics() -> None:
    assert H.evaluate_probe(H.CONTROL, False) is True
    assert H.evaluate_probe(H.CONTROL, True) is False
    assert H.evaluate_probe(H.TREATMENT, True) is True
    assert H.evaluate_probe(H.TREATMENT, False) is False
    assert H.evaluate_probe(H.TREATMENT, None) is None


# ---------------------------------------------------------------------------
# Installed-plugin-dir resolution
# ---------------------------------------------------------------------------


def test_resolve_plugin_dir_prefers_override(tmp_path: Path) -> None:
    override = tmp_path / "somewhere"
    assert (
        H.resolve_installed_plugin_dir(tmp_path / "cfg", "dev-team@bfinster", override)
        == override
    )


def test_resolve_plugin_dir_from_install_record(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    install = tmp_path / "install-here"
    install.mkdir()
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "plugins" / "installed_plugins.json").write_text(
        json.dumps(
            {"plugins": {"dev-team@bfinster": [
                {"scope": "project", "version": "10.11.0",
                 "installPath": str(install)}
            ]}}
        )
    )
    assert (
        H.resolve_installed_plugin_dir(cfg, "dev-team@bfinster") == install
    )


def test_resolve_plugin_dir_falls_back_to_version_cache(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    cached = cfg / "plugins" / "cache" / "bfinster" / "dev-team" / "10.11.0"
    cached.mkdir(parents=True)
    assert H.resolve_installed_plugin_dir(cfg, "dev-team@bfinster") == cached


def test_resolve_plugin_dir_ignores_similarly_named_plugin(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "plugins" / "installed_plugins.json").write_text(
        json.dumps(
            {"plugins": {"aci-dev-team@other": [
                {"installPath": str(tmp_path)}
            ]}}
        )
    )
    assert H.resolve_installed_plugin_dir(cfg, "dev-team@bfinster") is None
