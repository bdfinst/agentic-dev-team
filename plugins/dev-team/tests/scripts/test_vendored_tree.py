"""Unit tests for scripts/lib/_vendored_tree.py (issue #1420).

Exercises `is_vendored_dir`, `iter_files`, and `find_files` directly against
a fixture covering every name in `VENDORED_DIR_NAMES` (node_modules, .git,
vendor, dist, build), a pyvenv.cfg-marked virtualenv, and a symlinked file —
pinning pruning and symlink-skipping at the shared helper itself. This does
not invoke `detect_bdd_convention.py` or `gherkin_stub_gate.py` directly;
each of those scripts' own test files cover their own behavior built on top
of this shared helper.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import _vendored_tree


def _make_fixture(tmp_path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.go").write_text("")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "output.o").write_text("")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    (venv / "lib.py").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    (tmp_path / "src" / "linked.py").symlink_to(tmp_path / "src" / "app.py")
    return tmp_path


def test_is_vendored_dir_recognizes_every_named_dir_and_virtualenv_marker(tmp_path):
    fixture = _make_fixture(tmp_path)
    for name in sorted(_vendored_tree.VENDORED_DIR_NAMES):
        assert _vendored_tree.is_vendored_dir(fixture / name) is True, name
    assert _vendored_tree.is_vendored_dir(fixture / ".venv") is True
    assert _vendored_tree.is_vendored_dir(fixture / "src") is False


def test_iter_files_prunes_vendored_trees_and_skips_symlinked_files(tmp_path):
    fixture = _make_fixture(tmp_path)
    found = {p.relative_to(fixture).as_posix() for p in _vendored_tree.iter_files(fixture)}
    assert found == {"src/app.py"}


def test_find_files_applies_predicate_on_top_of_the_same_pruning(tmp_path):
    fixture = _make_fixture(tmp_path)
    found = _vendored_tree.find_files([fixture], lambda p: p.suffix == ".py")
    assert [p.relative_to(fixture).as_posix() for p in found] == ["src/app.py"]
