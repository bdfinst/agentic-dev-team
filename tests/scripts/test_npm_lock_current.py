"""Tests for scripts/npm_lock_current.py — is node_modules at the lockfile's versions.

`ci-local.sh` and `dev-setup.sh` run `npm ci` only when this says no, because
`npm ci` deletes `node_modules` and would race a test reading it.
"""

from __future__ import annotations

import json
import sys

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import npm_lock_current


def make_project(root, *, declared, locked, installed):
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps({"devDependencies": declared}), encoding="utf-8"
    )
    (root / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    f"node_modules/{name}": {"version": version}
                    for name, version in locked.items()
                }
            }
        ),
        encoding="utf-8",
    )
    for name, version in installed.items():
        pkg = root / "node_modules" / name
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(
            json.dumps({"version": version}), encoding="utf-8"
        )
    return root


def test_current_when_every_dev_dependency_is_installed_at_the_locked_version(tmp_path):
    project = make_project(
        tmp_path,
        declared={"eslint": "^9", "@scope/pkg": "1.0.0"},
        locked={"eslint": "9.39.4", "@scope/pkg": "1.0.0"},
        installed={"eslint": "9.39.4", "@scope/pkg": "1.0.0"},
    )
    assert npm_lock_current.main([str(project)]) == 0


def test_stale_when_an_installed_version_differs_from_the_lock(tmp_path):
    project = make_project(
        tmp_path,
        declared={"eslint": "^10"},
        locked={"eslint": "10.10.0"},
        installed={"eslint": "9.39.4"},
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_stale_when_a_dev_dependency_is_not_installed(tmp_path):
    project = make_project(
        tmp_path,
        declared={"eslint": "^9"},
        locked={"eslint": "9.39.4"},
        installed={},
    )
    assert npm_lock_current.main([str(project)]) == 1


def test_stale_when_the_lockfile_is_missing(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert npm_lock_current.main([str(tmp_path)]) == 1
