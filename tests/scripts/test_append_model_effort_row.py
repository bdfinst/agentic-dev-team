"""Tests for plugins/marketplace-dev/scripts/append_model_effort_row.py.

The script appends a `keep` row for a newly created agent to a repo's
model/effort decision log, and does nothing in a repo without that log.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

SCRIPT = (
    REPO_ROOT / "plugins" / "marketplace-dev" / "scripts" / "append_model_effort_row.py"
)
LOG_RELATIVE = Path("docs") / "model-effort-decisions.md"
AGENTS_RELATIVE = Path("plugins") / "demo" / "agents"
LOG_HEADER = """\
# Model and effort decision log

## Decisions

| Agent | Source | Baseline model | Baseline effort | Final model | Final effort | Decision | Fixtures | Evidence or reason | Eval cost saving (USD) |
|---|---|---|---|---|---|---|---|---|---|
"""


def keep_row(name: str, fixtures: int = 0, reason: str = "no fixture") -> str:
    source = (AGENTS_RELATIVE / f"{name}.md").as_posix()
    return (
        f"| {name} | {source} | haiku | medium | haiku | medium | keep | "
        f"{fixtures} | {reason} |  |\n"
    )


def make_repo(tmp_path: Path, rows: list[str] | None = None) -> Path:
    log = tmp_path / LOG_RELATIVE
    log.parent.mkdir(parents=True)
    rows = rows if rows is not None else [keep_row("alpha"), keep_row("zulu")]
    log.write_text(LOG_HEADER + "".join(rows) + "\n## Notes\n", encoding="utf-8")
    return tmp_path


def write_agent(
    root: Path, name: str, frontmatter: str = "model: sonnet\neffort: high"
) -> Path:
    path = root / AGENTS_RELATIVE / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8"
    )
    return path


def write_fixture(root: Path, stem: str, agent: str, directory: bool = False) -> None:
    expected = root / "evals" / "expected"
    expected.mkdir(parents=True, exist_ok=True)
    spec = {"fixture": stem, "applicableAgents": [agent], "agents": {agent: {}}}
    (expected / f"{stem}.json").write_text(json.dumps(spec), encoding="utf-8")
    fixtures = root / "evals" / "fixtures"
    if directory:
        (fixtures / stem).mkdir(parents=True)
    else:
        fixtures.mkdir(parents=True, exist_ok=True)
        (fixtures / f"{stem}.sql").write_text("SELECT 1;\n", encoding="utf-8")


def run_script(root: Path, agent: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(agent), "--repo-root", str(root)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LANG": "C.UTF-8"},
    )


def log_text(root: Path) -> str:
    return (root / LOG_RELATIVE).read_text(encoding="utf-8")


def test_repo_without_a_decision_log_is_left_untouched_and_silent(tmp_path):
    agent = write_agent(tmp_path, "beta")
    result = run_script(tmp_path, agent)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (tmp_path / LOG_RELATIVE).exists()


def test_agent_without_fixtures_gets_a_no_fixture_keep_row(tmp_path):
    root = make_repo(tmp_path)
    result = run_script(root, write_agent(root, "beta"))
    assert result.returncode == 0, result.stderr
    expected = (
        "| beta | plugins/demo/agents/beta.md | sonnet | high | sonnet | high | "
        "keep | 0 | no fixture |  |\n"
    )
    assert expected in log_text(root)


def test_row_is_inserted_in_name_order_within_the_table(tmp_path):
    root = make_repo(tmp_path)
    run_script(root, write_agent(root, "beta"))
    names = [
        line.split("|")[1].strip()
        for line in log_text(root).splitlines()
        if line.startswith("| ") and "plugins/demo" in line
    ]
    assert names == ["alpha", "beta", "zulu"]


def test_row_sorting_after_every_existing_row_goes_last_in_the_table(tmp_path):
    root = make_repo(tmp_path, rows=[keep_row("alpha")])
    run_script(root, write_agent(root, "omega"))
    table = [ln for ln in log_text(root).splitlines() if ln.startswith("|")]
    assert table[-1].startswith("| omega |")
    assert log_text(root).endswith("\n## Notes\n")


def test_fewer_than_three_fixtures_records_insufficient_fixtures(tmp_path):
    root = make_repo(tmp_path)
    write_fixture(root, "beta-one", "beta")
    write_fixture(root, "beta-two", "beta")
    write_fixture(root, "other", "alpha")
    run_script(root, write_agent(root, "beta"))
    assert "| keep | 2 | insufficient fixtures |  |" in log_text(root)


def test_three_runnable_fixtures_record_not_selected(tmp_path):
    root = make_repo(tmp_path)
    for stem in ("b1", "b2", "b3"):
        write_fixture(root, stem, "beta")
    run_script(root, write_agent(root, "beta"))
    assert "| keep | 3 | not selected |  |" in log_text(root)


def test_only_directory_fixtures_record_directory_fixtures_only(tmp_path):
    root = make_repo(tmp_path)
    for stem in ("b1", "b2", "b3"):
        write_fixture(root, stem, "beta", directory=True)
    run_script(root, write_agent(root, "beta"))
    assert "| keep | 3 | directory fixtures only |  |" in log_text(root)


def test_malformed_expected_file_is_not_counted(tmp_path):
    root = make_repo(tmp_path)
    write_fixture(root, "b1", "beta")
    (root / "evals" / "expected" / "broken.json").write_text("{beta", encoding="utf-8")
    run_script(root, write_agent(root, "beta"))
    assert "| keep | 1 | insufficient fixtures |  |" in log_text(root)


def test_agent_already_listed_is_not_added_twice(tmp_path):
    root = make_repo(tmp_path)
    before = log_text(root)
    result = run_script(root, write_agent(root, "alpha"))
    assert result.returncode == 0
    assert "already listed" in result.stdout
    assert log_text(root) == before


def test_agent_in_a_directory_the_log_does_not_track_is_skipped(tmp_path):
    root = make_repo(tmp_path)
    before = log_text(root)
    agent = root / "plugins" / "other" / "agents" / "beta.md"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        "---\nname: beta\nmodel: haiku\neffort: low\n---\n", encoding="utf-8"
    )
    result = run_script(root, agent)
    assert result.returncode == 0
    assert "does not track" in result.stdout
    assert log_text(root) == before


def test_agent_missing_model_or_effort_is_an_error(tmp_path):
    root = make_repo(tmp_path)
    before = log_text(root)
    result = run_script(root, write_agent(root, "beta", frontmatter="model: haiku"))
    assert result.returncode == 1
    assert "effort" in result.stderr
    assert log_text(root) == before


def load_gate():
    path = REPO_ROOT / "tests" / "docs" / "test_model_effort_decisions.py"
    spec = importlib.util.spec_from_file_location("model_effort_gate_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_appended_rows_pass_the_decision_log_gate(tmp_path):
    gate = load_gate()
    root = make_repo(tmp_path)
    write_fixture(root, "g1", "gamma")
    for stem in ("d1", "d2", "d3"):
        write_fixture(root, stem, "delta")
    for name in ("beta", "gamma", "delta"):
        run_script(root, write_agent(root, name))
    _, rows, parse_errors = gate.parse_log(log_text(root))
    assert parse_errors == []
    new_rows = [r for r in rows if r["Agent"] in {"beta", "gamma", "delta"}]
    assert len(new_rows) == 3
    for row in new_rows:
        frontmatter = (root / row["Source"]).read_text(encoding="utf-8")
        assert gate.check_row(row, lambda _source, fm=frontmatter: fm) == []


def test_model_or_effort_outside_the_gate_vocabulary_is_an_error(tmp_path):
    root = make_repo(tmp_path)
    before = log_text(root)
    for frontmatter in ("model: inherit\neffort: high", "model: haiku\neffort: ultra"):
        result = run_script(root, write_agent(root, "beta", frontmatter=frontmatter))
        assert result.returncode == 1
        assert "add the row by hand" in result.stderr
    assert log_text(root) == before


def test_last_table_row_without_a_newline_keeps_rows_separate(tmp_path):
    log = tmp_path / LOG_RELATIVE
    log.parent.mkdir(parents=True)
    log.write_text(LOG_HEADER + keep_row("alpha").rstrip("\n"), encoding="utf-8")
    run_script(tmp_path, write_agent(tmp_path, "beta"))
    table = [ln for ln in log_text(tmp_path).splitlines() if ln.startswith("|")]
    assert [row.split("|")[1].strip() for row in table[2:]] == ["alpha", "beta"]
