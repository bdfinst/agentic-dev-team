"""Every review agent has enough eval fixtures, hard fixtures and clean fixtures.

`scripts/eval_fixture_coverage.py` counts them per `plugins/dev-team/agents/*-review.md`
agent; the minimums and the hard/clean definitions live there and in
evals/README.md "Hard and clean fixtures".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

COVERAGE = REPO_ROOT / "scripts" / "eval_fixture_coverage.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COVERAGE), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_every_review_agent_meets_the_fixture_minimums() -> None:
    res = _run()
    assert res.returncode == 0, res.stdout + res.stderr


def _entry(agent: str, status: str, hard: bool) -> dict:
    expectation: dict = {"expectedStatus": status}
    if hard:
        expectation["hard"] = {"reason": "distractor", "note": "looks wrong, is not"}
    return {"fixture": "x", "applicableAgents": [agent], "agents": {agent: expectation}}


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    for name in ("agents", "expected", "fixtures"):
        (tmp_path / name).mkdir()
    (tmp_path / "agents" / "demo-review.md").write_text("---\nname: demo-review\n---\n")
    (tmp_path / "agents" / "helper.md").write_text("---\nname: helper\n---\n")
    return tmp_path


def _add(corpus: Path, stem: str, status: str, hard: bool = False) -> None:
    (corpus / "fixtures" / f"{stem}.ts").write_text("export {};\n")
    entry = _entry("demo-review", status, hard)
    (corpus / "expected" / f"{stem}.json").write_text(json.dumps(entry))


def _run_on(corpus: Path) -> subprocess.CompletedProcess:
    return _run(
        "--agents-dir",
        str(corpus / "agents"),
        "--expected-dir",
        str(corpus / "expected"),
        "--fixtures-dir",
        str(corpus / "fixtures"),
    )


def _meeting_minimums(corpus: Path) -> None:
    _add(corpus, "a", "fail", hard=True)
    _add(corpus, "b", "fail", hard=True)
    _add(corpus, "c", "pass")
    _add(corpus, "d", "fail")
    _add(corpus, "e", "warn")


def test_an_agent_at_the_minimums_passes(corpus: Path) -> None:
    _meeting_minimums(corpus)
    res = _run_on(corpus)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "demo-review" in res.stdout
    assert "helper" not in res.stdout  # only *-review agents are counted


def test_an_expected_skip_counts_as_clean(corpus: Path) -> None:
    _meeting_minimums(corpus)
    _add(corpus, "c", "skip")
    assert _run_on(corpus).returncode == 0


@pytest.mark.parametrize(
    ("stem", "status", "hard", "gap"),
    [
        ("e", None, False, "4/5 fixtures"),
        ("b", "fail", False, "1/2 hard"),
        ("c", "fail", False, "0/1 clean"),
    ],
)
def test_an_agent_below_a_minimum_fails_and_names_the_gap(
    corpus: Path, stem: str, status: str | None, hard: bool, gap: str
) -> None:
    _meeting_minimums(corpus)
    if status is None:
        (corpus / "expected" / f"{stem}.json").unlink()
    else:
        _add(corpus, stem, status, hard)
    res = _run_on(corpus)
    assert res.returncode == 1, res.stdout + res.stderr
    assert gap in res.stdout
    assert "demo-review" in res.stderr


def test_an_expected_entry_without_a_fixture_does_not_count(corpus: Path) -> None:
    _meeting_minimums(corpus)
    (corpus / "fixtures" / "e.ts").unlink()
    res = _run_on(corpus)
    assert res.returncode == 1
    assert "4/5 fixtures" in res.stdout
