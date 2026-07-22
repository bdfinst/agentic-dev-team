"""Tests for the long-eval restart-durable engine and CLI supervisor."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "long-eval"
sys.path.insert(0, str(SKILL_DIR))

import durable_runner  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SKILL_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# durable_runner engine
# --------------------------------------------------------------------------- #

def test_completes_all_cells_and_writes_done(tmp_path):
    cells = [(f"c{i}", i) for i in range(5)]
    done, summary = durable_runner.run_durable(
        cells, lambda p: p * 2, tmp_path, samples=3, workers=2,
        reduce=lambda s, k, p: {"sum": sum(s)},
        finalize=lambda d, o: {"cells": len(d)},
    )
    assert len(done) == 5
    assert done["c2"]["sum"] == 12  # 2*2 * 3 samples
    assert (tmp_path / "DONE").exists()
    assert json.loads((tmp_path / "summary.json").read_text()) == {"cells": 5}
    assert summary == {"cells": 5}


def test_resume_skips_banked_cells(tmp_path):
    (tmp_path / "cells.json").write_text(json.dumps({"a": {"pre": True}}))
    seen = []
    durable_runner.run_durable(
        [("a", "pa"), ("b", "pb")], lambda p: seen.append(p) or 1, tmp_path,
        samples=2, workers=1, reduce=lambda s, k, p: {"k": k},
    )
    # 'a' was already banked → its payload is never dispatched again.
    assert "pa" not in seen
    assert seen.count("pb") == 2
    done = json.loads((tmp_path / "cells.json").read_text())
    assert done["a"] == {"pre": True} and done["b"] == {"k": "b"}


def test_per_sample_checkpoint_preserves_partial(tmp_path):
    calls = {"n": 0}

    def flaky(_payload):
        calls["n"] += 1
        if calls["n"] == 3:            # die on the 3rd sample of the cell
            raise RuntimeError("recycle")
        return calls["n"]

    # First pass: cell banks 2 samples then the 3rd raises → cell stays unbanked
    # but the 2 partial samples are checkpointed.
    durable_runner.run_durable(
        [("a", "pa")], flaky, tmp_path, samples=5, workers=1,
    )
    assert not (tmp_path / "cells.json").exists() or \
        "a" not in json.loads((tmp_path / "cells.json").read_text())
    partial = json.loads((tmp_path / "samples.json").read_text())
    assert len(partial["a"]) == 2   # the 2 that landed before the raise

    # Second pass resumes: only 3 more samples are needed to reach samples=5.
    resumed = []
    done, _ = durable_runner.run_durable(
        [("a", "pa")], lambda p: resumed.append(p) or 9, tmp_path,
        samples=5, workers=1, finalize=lambda d, o: len(d),
    )
    assert len(resumed) == 3                     # 5 - 2 already banked
    assert done["a"]["n"] == 5                   # default reduce records n
    assert json.loads((tmp_path / "samples.json").read_text()) == {}  # cleared


def test_incomplete_run_writes_no_done(tmp_path):
    def poison(payload):
        if payload == "bad":
            raise ValueError("nope")
        return 1

    done, summary = durable_runner.run_durable(
        [("ok", "good"), ("bad", "bad")], poison, tmp_path,
        samples=1, workers=1, finalize=lambda d, o: "should-not-run",
    )
    assert "ok" in done and "bad" not in done
    assert summary is None
    assert not (tmp_path / "DONE").exists()
    assert not (tmp_path / "summary.json").exists()


def test_atomic_write_leaves_valid_json(tmp_path):
    p = tmp_path / "cells.json"
    durable_runner._atomic_write(p, {"x": 1})
    assert json.loads(p.read_text()) == {"x": 1}
    assert not (tmp_path / "cells.json.tmp").exists()


def test_status_counts(tmp_path):
    (tmp_path / "cells.json").write_text(json.dumps({"a": {}, "b": {}}))
    (tmp_path / "samples.json").write_text(json.dumps({"a": [1], "c": [1, 1]}))
    st = durable_runner.status(tmp_path)
    assert st["banked"] == 2
    assert st["partial_cells"] == 1        # 'c' only ('a' is banked)
    assert st["partial_samples"] == 2
    assert st["done"] is False


def test_flag_forces_progress_line(tmp_path):
    lines = []
    durable_runner.run_durable(
        [("a", 1)], lambda p: p, tmp_path, samples=1, workers=1,
        reduce=lambda s, k, p: {"bad": True},
        flag=lambda rec: rec.get("bad"), progress_every=999, logger=lines.append,
    )
    assert any("[1/1] a *" in ln for ln in lines)


# --------------------------------------------------------------------------- #
# run_eval CLI supervisor
# --------------------------------------------------------------------------- #

def test_cli_cells_and_module_loading(tmp_path):
    run_eval = _load("run_eval")
    mod_path = tmp_path / "m.py"
    mod_path.write_text(
        "CELLS = [('a', 1)]\n"
        "def sample(p):\n    return p\n"
    )
    mod = run_eval._load_module(mod_path)
    assert run_eval._cells(mod) == [("a", 1)]


def test_cli_cells_requires_definition(tmp_path):
    run_eval = _load("run_eval")
    mod_path = tmp_path / "empty.py"
    mod_path.write_text("x = 1\n")
    with pytest.raises(SystemExit):
        run_eval._cells(run_eval._load_module(mod_path))


def test_ensure_alive_noops_when_done(tmp_path, capsys):
    run_eval = _load("run_eval")
    (tmp_path / "DONE").write_text("")
    run_eval._ensure_alive(
        argparse.Namespace(out=str(tmp_path), module="x", samples=None,
                           workers=None, json=False)
    )
    assert "not relaunching" in capsys.readouterr().out


def test_live_pid_none_when_no_driver(tmp_path):
    run_eval = _load("run_eval")
    assert run_eval._live_pid(tmp_path) is None
