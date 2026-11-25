"""Tests for scripts/npm_lock_current.py — is node_modules at the lockfile's versions.

`ci-local.sh` and `dev-setup.sh` rely on this to decide whether `npm ci` is
needed, because `npm ci` deletes `node_modules` and would race a test reading it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts import npm_lock_current

SCRIPT = Path(npm_lock_current.__file__)


def make_project(
    root, *, locked, installed, optional=(), dev_optional=(), platform=(), links=()
):
    """`locked` and `installed` map a node_modules path (``a``, ``a/node_modules/b``)
    to a version. `platform` names the locked packages carrying `os`/`cpu`."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text("{}", encoding="utf-8")
    packages = {"": {"name": "demo"}}
    for name, version in locked.items():
        entry = {"version": version}
        if name in optional:
            entry["optional"] = True
        if name in dev_optional:
            entry["devOptional"] = True
        if name in platform:
            entry["os"], entry["cpu"] = ["darwin"], ["arm64"]
        packages[f"node_modules/{name}"] = entry
    for name in links:
        packages[f"node_modules/{name}"] = {"resolved": "../elsewhere", "link": True}
    (root / "package-lock.json").write_text(
        json.dumps({"packages": packages}), encoding="utf-8"
    )
    (root / "node_modules").mkdir()
    for name, version in installed.items():
        pkg = root / "node_modules" / name
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(
            json.dumps({"version": version}), encoding="utf-8"
        )
    return root


def test_current_when_every_locked_package_is_installed_at_its_locked_version(tmp_path):
    versions = {"eslint": "9.39.4", "@scope/pkg": "1.0.0"}
    project = make_project(tmp_path, locked=versions, installed=versions)
    assert npm_lock_current.main([str(project)]) == 0


def test_stale_when_an_installed_version_differs_from_the_lock(tmp_path):
    project = make_project(
        tmp_path, locked={"eslint": "10.10.0"}, installed={"eslint": "9.39.4"}
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_stale_when_only_a_transitive_package_differs_from_the_lock(tmp_path):
    project = make_project(
        tmp_path,
        locked={"eslint": "9.1.0", "dep": "2.0.0"},
        installed={"eslint": "9.1.0", "dep": "1.0.0"},
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_stale_when_a_nested_package_differs_from_the_lock(tmp_path):
    project = make_project(
        tmp_path,
        locked={"a": "1.0.0", "a/node_modules/b": "2.0.0"},
        installed={"a": "1.0.0", "a/node_modules/b": "3.0.0"},
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_stale_when_a_required_package_is_not_installed(tmp_path):
    project = make_project(
        tmp_path,
        locked={"eslint": "9.39.4", "dep": "1.0.0"},
        installed={"eslint": "9.39.4"},
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_current_when_only_a_platform_bound_optional_package_is_not_installed(
    tmp_path,
):
    project = make_project(
        tmp_path,
        locked={"eslint": "9.39.4", "fsevents": "2.3.3"},
        installed={"eslint": "9.39.4"},
        optional={"fsevents"},
        platform={"fsevents"},
    )
    assert npm_lock_current.main([str(project)]) == 0


def test_current_when_only_a_platform_bound_dev_optional_package_is_not_installed(
    tmp_path,
):
    project = make_project(
        tmp_path,
        locked={"eslint": "9.39.4", "fsevents": "2.3.3"},
        installed={"eslint": "9.39.4"},
        dev_optional={"fsevents"},
        platform={"fsevents"},
    )
    assert npm_lock_current.main([str(project)]) == 0


def test_stale_when_a_dev_optional_package_without_platform_limits_is_not_installed(
    tmp_path,
):
    """`devOptional` is the overlap of the dev and optional trees: `npm ci`
    installs it, so only an `os`/`cpu` mismatch can excuse its absence."""
    project = make_project(
        tmp_path,
        locked={"eslint": "9.39.4", "dep": "1.0.0"},
        installed={"eslint": "9.39.4"},
        dev_optional={"dep"},
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_stale_when_an_optional_package_without_platform_limits_is_not_installed(
    tmp_path,
):
    project = make_project(
        tmp_path,
        locked={"eslint": "9.39.4", "dep": "1.0.0"},
        installed={"eslint": "9.39.4"},
        optional={"dep"},
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_a_linked_entry_is_not_compared(tmp_path):
    project = make_project(
        tmp_path,
        locked={"eslint": "9.39.4"},
        installed={"eslint": "9.39.4"},
        links=["ws"],
    )
    assert npm_lock_current.main([str(project)]) == 0


def test_stale_when_node_modules_is_missing(tmp_path):
    project = make_project(tmp_path, locked={}, installed={})
    (project / "node_modules").rmdir()
    assert npm_lock_current.main([str(project)]) == 1


def test_stale_when_the_lockfile_is_missing(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert npm_lock_current.main([str(tmp_path)]) == 1


def test_a_malformed_lockfile_exits_1_without_a_traceback(tmp_path):
    (tmp_path / "package-lock.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
