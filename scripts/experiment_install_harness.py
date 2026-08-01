#!/usr/bin/env python3
"""Experiment install harness — release vs. experiment-branch plugin, side by side.

Provisions two isolated test projects and installs the dev-team plugin into
each from a *different* source, so A/B arms B and C (epic #1097) run against
genuinely different plugin builds with everything else held constant:

  * **Control (arm B)** — the *released* plugin from the published marketplace:
    ``claude plugin marketplace add bdfinst/agentic-dev-team`` +
    ``claude plugin install dev-team@bfinster``.
  * **Treatment (arm C)** — the *experiment-branch* build from a local
    checkout: ``claude plugin marketplace add <checkout>`` +
    ``claude plugin install --scope project dev-team@bfinster``.

Each arm gets its own ``CLAUDE_CONFIG_DIR`` (under ``--workdir`` by default).
This is what makes side-by-side possible at all: Claude Code's plugin cache is
version-keyed (``<config>/plugins/cache/<marketplace>/dev-team/<version>/``),
so a branch build carrying the same version string as the release would
collide with — and silently reuse — the released cache if both arms shared
one ``~/.claude``. Separate config dirs remove the collision by construction.

After installing, a deterministic **probe** confirms each project loaded the
intended build: the experiment branch ships a marker
(``knowledge/fanout-economics.md``, added by #1092/#1093) that the release
does not have. The probe checks for the marker inside the *installed* plugin
directory of each arm — present in treatment, absent in control.

Emits a JSON manifest recording, per arm: install source, resolved SHA /
release tag, plugin version, install commands, probe result, timestamps, and
recorded-at-runtime placeholders for the band→model map
(``/model-routing-check`` output, which needs a live session).

Exit codes:
    0  everything requested succeeded (installs + probes, or dry-run)
    1  an install command failed (its exit code and stderr were surfaced)
    2  a verification probe failed (wrong build loaded)
    3  environment error (``claude`` CLI missing, bad paths, …)

Stdlib only, Python 3.8+. Dev tooling — not shipped with the plugin.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_MARKETPLACE_SLUG = "bdfinst/agentic-dev-team"
DEFAULT_PLUGIN_ID = "dev-team@bfinster"
DEFAULT_MARKER = "knowledge/fanout-economics.md"
CONTROL, TREATMENT = "control", "treatment"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plugin_name(plugin_id: str) -> str:
    return plugin_id.split("@", 1)[0]


def _marketplace_name(plugin_id: str) -> str:
    return plugin_id.split("@", 1)[1] if "@" in plugin_id else plugin_id


# ---------------------------------------------------------------------------
# Command construction (pure — unit-testable, and what --dry-run prints)
# ---------------------------------------------------------------------------

def build_install_commands(arm: str, source: str, plugin_id: str) -> list[list[str]]:
    """The exact ``claude`` invocations for one arm, in order.

    ``source`` is the marketplace to add: the published GitHub slug for
    control, the experiment-branch checkout path for treatment.
    """
    if arm == CONTROL:
        return [
            ["claude", "plugin", "marketplace", "add", source],
            ["claude", "plugin", "install", plugin_id],
        ]
    if arm == TREATMENT:
        return [
            ["claude", "plugin", "marketplace", "add", source],
            ["claude", "plugin", "install", "--scope", "project", plugin_id],
        ]
    raise ValueError(f"unknown arm: {arm}")


# ---------------------------------------------------------------------------
# Subprocess plumbing — never swallow stderr, always propagate nonzero exits
# ---------------------------------------------------------------------------

def run_command(cmd: list[str], cwd: Path, config_dir: Path) -> subprocess.CompletedProcess:
    """Run one install command with the arm's isolated CLAUDE_CONFIG_DIR.

    Output is captured *and re-emitted* (stdout→stdout, stderr→stderr) so
    nothing is swallowed while the manifest can still record it. Raises
    ``CalledProcessError`` on nonzero exit.
    """
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    proc = subprocess.run(
        cmd, cwd=str(cwd), env=env, capture_output=True, text=True, check=False
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr
        )
    return proc


def git_head_sha(repo_dir: Path) -> str | None:
    """``git rev-parse HEAD`` in ``repo_dir``; None (with a stderr note) if it
    is not a git repo or git is unavailable. Never raises."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
    except OSError as exc:  # git missing entirely
        print(f"warning: git unavailable ({exc}); SHA not recorded", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(
            f"warning: could not resolve HEAD in {repo_dir}: {proc.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Locating the installed plugin on disk
# ---------------------------------------------------------------------------

def resolve_installed_plugin_dir(
    config_dir: Path, plugin_id: str, override: Path | None = None
) -> Path | None:
    """Where the installed plugin's files materialized for this arm.

    Resolution order:
      1. explicit ``--*-plugin-dir`` override;
      2. ``installPath`` from ``<config>/plugins/installed_plugins.json``
         (Claude Code's install record — see CONTRIBUTING.md);
      3. the version-keyed cache
         ``<config>/plugins/cache/<marketplace>/<plugin>/<version>/``
         (newest entry). This layout is observed with Claude Code v2.1.x and
         is version-dependent — hence the override flag.
    """
    if override is not None:
        return override

    name = _plugin_name(plugin_id)
    record_path = config_dir / "plugins" / "installed_plugins.json"
    try:
        record = json.loads(record_path.read_text())
    except (OSError, ValueError):
        record = {}
    for pid, entries in (record.get("plugins") or {}).items():
        if pid.split("@", 1)[0] != name:
            continue
        if isinstance(entries, dict):  # older single-entry shape
            entries = [entries]
        for entry in entries or []:
            if isinstance(entry, dict) and entry.get("installPath"):
                p = Path(entry["installPath"])
                if p.is_dir():
                    return p

    cache_root = config_dir / "plugins" / "cache"
    candidates = sorted(
        cache_root.glob(f"*/{name}/*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for c in candidates:
        if c.is_dir():
            return c
    return None


def installed_plugin_version(
    config_dir: Path, plugin_id: str, plugin_dir: Path | None
) -> str | None:
    """Plugin version, from the install record or the installed plugin.json."""
    name = _plugin_name(plugin_id)
    record_path = config_dir / "plugins" / "installed_plugins.json"
    try:
        record = json.loads(record_path.read_text())
        for pid, entries in (record.get("plugins") or {}).items():
            if pid.split("@", 1)[0] != name:
                continue
            if isinstance(entries, dict):
                entries = [entries]
            for entry in entries or []:
                if isinstance(entry, dict) and entry.get("version"):
                    return str(entry["version"])
    except (OSError, ValueError):
        pass
    if plugin_dir is not None:
        try:
            manifest = json.loads(
                (plugin_dir / ".claude-plugin" / "plugin.json").read_text()
            )
            if manifest.get("version"):
                return str(manifest["version"])
        except (OSError, ValueError):
            pass
    return None


def checkout_plugin_version(checkout: Path) -> str | None:
    """Version straight from the experiment checkout's plugin manifest."""
    for rel in ("plugins/dev-team/.claude-plugin/plugin.json",
                ".claude-plugin/plugin.json"):
        try:
            manifest = json.loads((checkout / rel).read_text())
            if manifest.get("version"):
                return str(manifest["version"])
        except (OSError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# Verification probe
# ---------------------------------------------------------------------------

def probe_marker(
    plugin_dir: Path | None, marker: str, marker_string: str | None = None
) -> bool | None:
    """Is the treatment marker present in this installed plugin dir?

    Returns True/False, or None when the installed dir could not be located
    (probe inconclusive). With ``marker_string``, the marker file must both
    exist and contain the string.
    """
    if plugin_dir is None:
        return None
    target = plugin_dir / marker
    if not target.is_file():
        return False
    if marker_string is None:
        return True
    try:
        return marker_string in target.read_text(errors="replace")
    except OSError:
        return False


def evaluate_probe(arm: str, present: bool | None) -> bool | None:
    """Pass/fail: marker present in treatment, absent in control. None while
    inconclusive (installed dir not found / dry-run)."""
    if present is None:
        return None
    expected = arm == TREATMENT
    return present == expected


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def band_model_placeholder() -> dict[str, Any]:
    """Recorded-at-runtime placeholder for the band→model map.

    ``/model-routing-check`` runs inside a live Claude Code session against
    the installed plugin's model ladder; it is not automatable from this
    headless harness. The Phase 3 executor (#1099) fills ``bands`` by running
    the skill in each arm's session and pasting the mapping here.
    """
    return {
        "recorded_at_runtime": True,
        "source": "/model-routing-check",
        "bands": None,
        "note": (
            "Run /model-routing-check in a session opened inside this arm's "
            "project and record the band->model mapping here before the arm's "
            "measured runs."
        ),
    }


def build_arm_manifest(
    arm: str,
    *,
    project_dir: Path,
    config_dir: Path,
    source: str,
    commands: list[list[str]],
    plugin_id: str,
    executed: bool,
    plugin_version: str | None = None,
    resolved_sha: str | None = None,
    release_tag: str | None = None,
    installed_plugin_dir: Path | None = None,
    marker: str = DEFAULT_MARKER,
    marker_string: str | None = None,
    marker_present: bool | None = None,
) -> dict[str, Any]:
    return {
        "arm": "B" if arm == CONTROL else "C",
        "role": arm,
        "project_dir": str(project_dir),
        "claude_config_dir": str(config_dir),
        "plugin_id": plugin_id,
        "install_source": source,
        "install_scope": "user" if arm == CONTROL else "project",
        "commands": commands,
        "executed": executed,
        "installed_at": _now_iso() if executed else None,
        "plugin_version": plugin_version,
        "resolved_sha": resolved_sha,
        "release_tag": release_tag,
        "installed_plugin_dir": (
            str(installed_plugin_dir) if installed_plugin_dir else None
        ),
        "probe": {
            "marker": marker,
            "marker_string": marker_string,
            "expected_present": arm == TREATMENT,
            "present": marker_present,
            "passed": evaluate_probe(arm, marker_present),
        },
        "band_model_map": band_model_placeholder(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="experiment_install_harness.py",
        description=(
            "Provision two isolated test projects with the released (control, "
            "arm B) and experiment-branch (treatment, arm C) dev-team plugin "
            "builds, verify each loaded the intended build, and emit a JSON "
            "manifest. Epic #1097."
        ),
    )
    p.add_argument(
        "--workdir",
        type=Path,
        default=Path("experiment-harness-work"),
        help="Root for default project/config/manifest paths "
        "(default: ./experiment-harness-work)",
    )
    p.add_argument(
        "--experiment-checkout",
        type=Path,
        help="Path to the experiment-branch checkout of the marketplace repo "
        "(required unless --control-only)",
    )
    p.add_argument("--control-project", type=Path,
                   help="Test project A dir (default: <workdir>/control-project)")
    p.add_argument("--treatment-project", type=Path,
                   help="Test project B dir (default: <workdir>/treatment-project)")
    p.add_argument("--control-config-dir", type=Path,
                   help="CLAUDE_CONFIG_DIR for the control arm "
                   "(default: <workdir>/control-claude-config)")
    p.add_argument("--treatment-config-dir", type=Path,
                   help="CLAUDE_CONFIG_DIR for the treatment arm "
                   "(default: <workdir>/treatment-claude-config)")
    only = p.add_mutually_exclusive_group()
    only.add_argument("--control-only", action="store_true",
                      help="Provision only the control arm (B)")
    only.add_argument("--treatment-only", action="store_true",
                      help="Provision only the treatment arm (C)")
    p.add_argument("--marketplace-slug", default=DEFAULT_MARKETPLACE_SLUG,
                   help="Published marketplace for the control install "
                   "(default: %(default)s)")
    p.add_argument("--plugin-id", default=DEFAULT_PLUGIN_ID,
                   help="Plugin id to install (default: %(default)s)")
    p.add_argument("--marker", default=DEFAULT_MARKER,
                   help="Treatment marker path, relative to the installed "
                   "plugin root (default: %(default)s)")
    p.add_argument("--marker-string",
                   help="Optional string the marker file must also contain")
    p.add_argument("--control-plugin-dir", type=Path,
                   help="Override: where the control arm's installed plugin "
                   "materialized (skips auto-detection)")
    p.add_argument("--treatment-plugin-dir", type=Path,
                   help="Override: where the treatment arm's installed plugin "
                   "materialized (skips auto-detection)")
    p.add_argument("--manifest", type=Path,
                   help="Manifest output path "
                   "(default: <workdir>/experiment-manifest.json)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the commands without executing them (claude "
                   "CLI not required); probes are skipped")
    args = p.parse_args(argv)

    args.control_project = args.control_project or args.workdir / "control-project"
    args.treatment_project = (
        args.treatment_project or args.workdir / "treatment-project"
    )
    args.control_config_dir = (
        args.control_config_dir or args.workdir / "control-claude-config"
    )
    args.treatment_config_dir = (
        args.treatment_config_dir or args.workdir / "treatment-claude-config"
    )
    args.manifest = args.manifest or args.workdir / "experiment-manifest.json"

    if not args.control_only and args.experiment_checkout is None:
        p.error("--experiment-checkout is required unless --control-only")
    return args


def _provision_arm(args: argparse.Namespace, arm: str) -> tuple[dict[str, Any], int]:
    """Provision one arm end to end. Returns (arm manifest, worst exit code)."""
    if arm == CONTROL:
        project, cfg = args.control_project, args.control_config_dir
        source = args.marketplace_slug
        override = args.control_plugin_dir
    else:
        project, cfg = args.treatment_project, args.treatment_config_dir
        source = str(args.experiment_checkout.resolve())
        override = args.treatment_plugin_dir

    commands = build_install_commands(arm, source, args.plugin_id)

    if args.dry_run:
        print(f"[{arm}] (dry-run) in {project} with CLAUDE_CONFIG_DIR={cfg}:")
        for cmd in commands:
            print("  $ " + " ".join(cmd))
        version = sha = None
        if arm == TREATMENT and args.experiment_checkout.is_dir():
            version = checkout_plugin_version(args.experiment_checkout)
        manifest = build_arm_manifest(
            arm, project_dir=project, config_dir=cfg, source=source,
            commands=commands, plugin_id=args.plugin_id, executed=False,
            plugin_version=version, resolved_sha=sha,
            marker=args.marker, marker_string=args.marker_string,
        )
        return manifest, 0

    if arm == TREATMENT and not args.experiment_checkout.is_dir():
        print(
            f"error: --experiment-checkout {args.experiment_checkout} is not a directory",
            file=sys.stderr,
        )
        return build_arm_manifest(
            arm, project_dir=project, config_dir=cfg, source=source,
            commands=commands, plugin_id=args.plugin_id, executed=False,
            marker=args.marker, marker_string=args.marker_string,
        ), 3

    project.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    executed = True
    for cmd in commands:
        print("[{}] $ {}  (cwd={})".format(arm, " ".join(cmd), project))
        try:
            run_command(cmd, cwd=project, config_dir=cfg)
        except subprocess.CalledProcessError as exc:
            print(
                f"error: [{arm}] command {' '.join(cmd)!r} exited {exc.returncode}",
                file=sys.stderr,
            )
            executed = False
            exit_code = 1
            break

    plugin_dir = resolve_installed_plugin_dir(cfg, args.plugin_id, override)
    version = installed_plugin_version(cfg, args.plugin_id, plugin_dir)

    if arm == TREATMENT:
        sha = git_head_sha(args.experiment_checkout)
        release_tag = None
        if version is None:
            version = checkout_plugin_version(args.experiment_checkout)
    else:
        marketplace_clone = (
            cfg / "plugins" / "marketplaces" / _marketplace_name(args.plugin_id)
        )
        sha = git_head_sha(marketplace_clone) if marketplace_clone.is_dir() else None
        release_tag = (
            f"{_plugin_name(args.plugin_id)}-v{version}" if version else None
        )

    present = probe_marker(plugin_dir, args.marker, args.marker_string) if executed else None
    manifest = build_arm_manifest(
        arm, project_dir=project, config_dir=cfg, source=source,
        commands=commands, plugin_id=args.plugin_id, executed=executed,
        plugin_version=version, resolved_sha=sha, release_tag=release_tag,
        installed_plugin_dir=plugin_dir,
        marker=args.marker, marker_string=args.marker_string,
        marker_present=present,
    )

    passed = manifest["probe"]["passed"]
    if executed and passed is False:
        print(
            "error: [{}] probe FAILED — marker {!r} {} in {} (expected {}). "
            "Wrong build loaded.".format(
                arm,
                args.marker,
                "present" if present else "absent",
                plugin_dir,
                "present" if arm == TREATMENT else "absent",
            ),
            file=sys.stderr,
        )
        exit_code = max(exit_code, 2)
    elif executed and passed is None:
        print(
            f"warning: [{arm}] probe inconclusive — installed plugin dir not "
            f"found under {cfg}; pass --{arm}-plugin-dir to point the probe at it",
            file=sys.stderr,
        )
        exit_code = max(exit_code, 2)
    elif executed:
        print("[{}] probe OK: marker {} as expected".format(arm, "present" if present else "absent"))
    return manifest, exit_code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.dry_run and shutil.which("claude") is None:
        print(
            "error: the `claude` CLI is not on PATH. Install Claude Code "
            "(https://code.claude.com/docs) or re-run with --dry-run to "
            "preview the commands.",
            file=sys.stderr,
        )
        return 3

    arms: dict[str, Any] = {}
    exit_code = 0
    if not args.treatment_only:
        manifest, code = _provision_arm(args, CONTROL)
        arms[CONTROL] = manifest
        exit_code = max(exit_code, code)
    if not args.control_only:
        manifest, code = _provision_arm(args, TREATMENT)
        arms[TREATMENT] = manifest
        exit_code = max(exit_code, code)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "harness": "scripts/experiment_install_harness.py",
        "epic": "#1097",
        "dry_run": args.dry_run,
        "arms": arms,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"manifest: {args.manifest}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
