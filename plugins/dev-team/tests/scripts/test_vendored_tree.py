"""Unit tests for scripts/lib/_vendored_tree.py (issue #1420).

Regression-safety-net for the extraction from detect_bdd_convention.py and
gherkin_stub_gate.py: asserts both callers' pruning behavior stays identical
for a fixture containing node_modules/, .git/, and a pyvenv.cfg-marked
directory.
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
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    (venv / "lib.py").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    return tmp_path


def test_is_vendored_dir_recognizes_named_dirs_and_virtualenv_marker(tmp_path):
    fixture = _make_fixture(tmp_path)
    assert _vendored_tree.is_vendored_dir(fixture / "node_modules") is True
    assert _vendored_tree.is_vendored_dir(fixture / ".git") is True
    assert _vendored_tree.is_vendored_dir(fixture / ".venv") is True
    assert _vendored_tree.is_vendored_dir(fixture / "src") is False


def test_iter_files_prunes_vendored_trees(tmp_path):
    fixture = _make_fixture(tmp_path)
    found = {p.relative_to(fixture).as_posix() for p in _vendored_tree.iter_files(fixture)}
    assert found == {"src/app.py"}
