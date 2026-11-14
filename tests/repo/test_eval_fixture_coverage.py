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


def _row(stdout: str, agent: str) -> str:
    (line,) = [ln for ln in stdout.splitlines() if ln.split()[:1] == [agent]]
    return " ".join(line.split())


@pytest.mark.parametrize(
    ("stem", "status", "hard", "row"),
    [
        ("e", None, False, "demo-review 4 2 1 4/5 fixtures"),
        ("b", "fail", False, "demo-review 5 1 1 1/2 hard"),
        ("c", "fail", False, "demo-review 5 2 0 0/1 clean"),
        ("c", "warn", False, "demo-review 5 2 0 0/1 clean"),
    ],
)
def test_an_agent_below_a_minimum_fails_and_names_the_gap(
    corpus: Path, stem: str, status: str | None, hard: bool, row: str
) -> None:
    _meeting_minimums(corpus)
    if status is None:
        (corpus / "expected" / f"{stem}.json").unlink()
    else:
        _add(corpus, stem, status, hard)
    res = _run_on(corpus)
    assert res.returncode == 1, res.stdout + res.stderr
    assert _row(res.stdout, "demo-review") == row
    assert "1 review agent(s) below the minimum: demo-review" in res.stderr


def test_an_expectation_without_a_status_is_not_clean(corpus: Path) -> None:
    _meeting_minimums(corpus)
    entry = {"fixture": "c", "agents": {"demo-review": {}}}
    (corpus / "expected" / "c.json").write_text(json.dumps(entry))
    res = _run_on(corpus)
    assert res.returncode == 1
    assert _row(res.stdout, "demo-review") == "demo-review 5 2 0 0/1 clean"


def test_a_hard_null_marker_is_not_hard(corpus: Path) -> None:
    _meeting_minimums(corpus)
    entry = _entry("demo-review", "fail", hard=False)
    entry["agents"]["demo-review"]["hard"] = None
    (corpus / "expected" / "b.json").write_text(json.dumps(entry))
    res = _run_on(corpus)
    assert _row(res.stdout, "demo-review") == "demo-review 5 1 1 1/2 hard"


def test_an_expected_entry_without_a_fixture_does_not_count(corpus: Path) -> None:
    _meeting_minimums(corpus)
    (corpus / "fixtures" / "a.ts").unlink()  # a hard fixture
    res = _run_on(corpus)
    assert res.returncode == 1
    assert _row(res.stdout, "demo-review") == (
        "demo-review 4 1 1 4/5 fixtures, 1/2 hard"
    )


def test_a_directory_fixture_counts_by_its_name(corpus: Path) -> None:
    _meeting_minimums(corpus)
    (corpus / "fixtures" / "e.ts").unlink()
    (corpus / "fixtures" / "e").mkdir()
    (corpus / "fixtures" / "e" / "index.ts").write_text("export {};\n")
    res = _run_on(corpus)
    assert res.returncode == 0, res.stdout + res.stderr
    assert _row(res.stdout, "demo-review") == "demo-review 5 2 1 -"


def test_a_review_agent_with_no_entries_is_named(corpus: Path) -> None:
    _meeting_minimums(corpus)
    (corpus / "agents" / "idle-review.md").write_text("---\nname: idle-review\n---\n")
    res = _run_on(corpus)
    assert res.returncode == 1
    assert _row(res.stdout, "idle-review") == (
        "idle-review 0 0 0 0/5 fixtures, 0/2 hard, 0/1 clean"
    )
    assert "1 review agent(s) below the minimum: idle-review" in res.stderr


@pytest.mark.parametrize("missing", ["agents", "expected", "fixtures"])
def test_a_missing_directory_exits_2_naming_it(corpus: Path, missing: str) -> None:
    (corpus / missing).rename(corpus / f"{missing}-gone")
    res = _run_on(corpus)
    assert res.returncode == 2
    assert f"directory not found: {corpus / missing}" in res.stderr


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("{not json", "not valid JSON"),
        ("[1, 2]", "not a JSON object"),
        ('{"agents": []}', "`agents` is not a JSON object"),
    ],
)
def test_a_malformed_expected_file_exits_2_naming_it(
    corpus: Path, content: str, reason: str
) -> None:
    _meeting_minimums(corpus)
    (corpus / "expected" / "c.json").write_text(content)
    res = _run_on(corpus)
    assert res.returncode == 2
    assert "Traceback" not in res.stderr
    assert f"malformed expected file c.json: {reason}" in res.stderr


def test_a_malformed_expected_file_without_a_fixture_exits_2(corpus: Path) -> None:
    _meeting_minimums(corpus)
    (corpus / "expected" / "orphan.json").write_text('{"agents": null}')
    res = _run_on(corpus)
    assert res.returncode == 2
    assert "malformed expected file orphan.json: `agents` is not a JSON object" in (
        res.stderr
    )


def test_a_non_utf8_expected_file_exits_2(corpus: Path) -> None:
    _meeting_minimums(corpus)
    (corpus / "expected" / "latin.json").write_bytes(b'{"description": "caf\xe9"}')
    res = _run_on(corpus)
    assert res.returncode == 2
    assert "malformed expected file latin.json: not valid JSON" in res.stderr


def test_an_agent_without_a_review_agent_file_is_ignored(corpus: Path) -> None:
    _meeting_minimums(corpus)
    entry = _entry("demo-review", "fail", hard=True)
    entry["agents"]["helper"] = {"expectedStatus": "pass"}
    entry["agents"]["ghost-review"] = {"expectedStatus": "pass"}
    (corpus / "expected" / "a.json").write_text(json.dumps(entry))
    res = _run_on(corpus)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Traceback" not in res.stderr
    assert _row(res.stdout, "demo-review") == "demo-review 5 2 1 -"


@pytest.mark.parametrize("expectation", [None, "pass", ["pass"]])
def test_a_non_object_expectation_is_not_counted(corpus: Path, expectation: object) -> None:
    _meeting_minimums(corpus)
    entry = {"fixture": "e", "agents": {"demo-review": expectation}}
    (corpus / "expected" / "e.json").write_text(json.dumps(entry))
    res = _run_on(corpus)
    assert "Traceback" not in res.stderr
    assert _row(res.stdout, "demo-review") == "demo-review 4 2 1 4/5 fixtures"


def test_an_entry_without_an_agents_block_is_not_counted(corpus: Path) -> None:
    _meeting_minimums(corpus)
    (corpus / "expected" / "e.json").write_text(json.dumps({"fixture": "e"}))
    res = _run_on(corpus)
    assert "Traceback" not in res.stderr
    assert _row(res.stdout, "demo-review") == "demo-review 4 2 1 4/5 fixtures"
