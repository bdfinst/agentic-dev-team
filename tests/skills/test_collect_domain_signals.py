"""Pytest tests for collect_domain_signals.py (#617 / #572 Phase 3).

The port INTENTIONALLY diverges from the .sh behavior: the shipped
`collect-domain-signals.sh` aborts under `set -euo pipefail` after the
first section whose intermediate grep chain finds no matches (an empty
`grep -v` in the pipeline returns exit 1 → pipefail → set -e → exit).
That leaves only `class-names.txt` written even on a real project.

The Python port avoids that trap and produces all six output files.
This is a conscious behavior fix — the .sh has zero bats coverage today,
so nothing depends on the buggy early-exit behavior; the ubiquitous-
language skill only ever wanted the full six-file signal set.

These tests validate the intended contract: given a source tree with
domain symbols, all six output files exist under
`.plans/raw/domain-language/` and contain the expected candidates.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPT_PY = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "ubiquitous-language"
    / "scripts"
    / "collect_domain_signals.py"
)


def _run(*, root: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), root],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LANG": "C.UTF-8"},
    )


def _mk_project(tree: Path) -> None:
    """Create a mini project with symbols the collector should find."""
    src = tree / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.ts").write_text(
        "export class Customer {}\n"
        "export class Order {}\n"
        "export class OrderCreated {}\n"
        "export class OrderRepository {}\n"
        "export interface PaymentGateway {}\n"
        "export interface UserRepository {}\n"
        "export enum Status { Active }\n"
        "it('does the thing')\n"
        "z.string().refine(x => x)\n"
    )
    (src / "a.py").write_text(
        "class Foo:\n    pass\n"
        "class BarStatus(Enum):\n    pass\n"
        "raise ValueError('bad')\n"
    )
    (src / "a.feature").write_text("Scenario: Sample\n  Given something\n")


def test_all_six_output_files_exist(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workdir = tmp_path / "work"
    workdir.mkdir()
    _mk_project(project)
    r = _run(root=str(project), cwd=workdir)
    assert r.returncode == 0, r.stderr
    out = workdir / ".plans" / "raw" / "domain-language"
    for name in (
        "class-names.txt",
        "enum-values.txt",
        "domain-events.txt",
        "bdd-names.txt",
        "validator-rules.txt",
        "interface-names.txt",
    ):
        assert (out / name).is_file(), f"missing {name}"


def test_class_names_filters_excluded_terms(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workdir = tmp_path / "work"
    workdir.mkdir()
    _mk_project(project)
    _run(root=str(project), cwd=workdir)
    class_names = (workdir / ".plans/raw/domain-language/class-names.txt").read_text()
    # Domain nouns are extracted:
    assert "Customer" in class_names
    assert "Order" in class_names
    # Infrastructure-y names filtered out (contains "Repository"):
    assert "OrderRepository" not in class_names
    assert "UserRepository" not in class_names


def test_domain_events_extracted(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workdir = tmp_path / "work"
    workdir.mkdir()
    _mk_project(project)
    _run(root=str(project), cwd=workdir)
    events = (workdir / ".plans/raw/domain-language/domain-events.txt").read_text()
    assert "OrderCreated" in events


def test_interface_names_filtered(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workdir = tmp_path / "work"
    workdir.mkdir()
    _mk_project(project)
    _run(root=str(project), cwd=workdir)
    ifaces = (workdir / ".plans/raw/domain-language/interface-names.txt").read_text()
    assert "PaymentGateway" in ifaces
    assert "UserRepository" not in ifaces


def test_bdd_scenarios_captured(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workdir = tmp_path / "work"
    workdir.mkdir()
    _mk_project(project)
    _run(root=str(project), cwd=workdir)
    bdd = (workdir / ".plans/raw/domain-language/bdd-names.txt").read_text()
    assert "Scenario: Sample" in bdd
    assert "Given" in bdd or "it('does the thing')" in bdd


def test_validator_rules_captured(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workdir = tmp_path / "work"
    workdir.mkdir()
    _mk_project(project)
    _run(root=str(project), cwd=workdir)
    vr = (workdir / ".plans/raw/domain-language/validator-rules.txt").read_text()
    # The Python raise ValueError line should be captured.
    assert "raise ValueError" in vr


def test_empty_project_produces_empty_files(tmp_path: Path) -> None:
    """The port avoids the .sh's set-e trap: even with zero matches, all
    six output files exist (they will just be empty). This IS a divergence
    from the .sh; the docstring / commit message call it out explicitly."""
    empty = tmp_path / "empty_project"
    empty.mkdir()
    workdir = tmp_path / "work"
    workdir.mkdir()
    r = _run(root=str(empty), cwd=workdir)
    assert r.returncode == 0
    for name in (
        "class-names.txt",
        "enum-values.txt",
        "domain-events.txt",
        "bdd-names.txt",
        "validator-rules.txt",
        "interface-names.txt",
    ):
        p = workdir / ".plans/raw/domain-language" / name
        assert p.is_file()
        assert p.read_text() == ""


def test_defaults_to_cwd(tmp_path: Path) -> None:
    project = tmp_path / "cwd_project"
    _mk_project(project)
    r = subprocess.run(
        [sys.executable, str(_SCRIPT_PY)],
        cwd=str(project),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert (project / ".plans/raw/domain-language/class-names.txt").is_file()
