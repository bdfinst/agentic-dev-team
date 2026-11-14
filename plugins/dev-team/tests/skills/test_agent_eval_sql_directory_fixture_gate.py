"""agent-eval/SKILL.md's sql-review detector pre-phase covers directory fixtures.

The detector does not expand a directory path, so a directory fixture passed
as-is yields no hits and the agent has nothing to triage. The skill passes a
directory fixture's files through ``--files-from -``. These tests run that form
against the real directory fixtures and check that each yields the detector
hit its distractor depends on.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "agent-eval" / "SKILL.md"
DETECTOR = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "sql_anti_patterns.py"
FIXTURES = REPO_ROOT / "evals" / "fixtures"


def _gate_over_directory_files(directory):
    files = sorted(str(path) for path in directory.rglob("*") if path.is_file())
    proc = subprocess.run(
        [sys.executable, str(DETECTOR), "--gate", "--files-from", "-"],
        input="\n".join(files) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_skill_passes_a_directory_fixtures_files_to_the_gate() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "find <fixture-path> -type f" in text
    assert "--gate --files-from -" in text


@pytest.mark.parametrize(
    ("stem", "hit_file", "rule"),
    [
        (
            "sql-not-in-not-null-migration",
            "queries/fulfilment_report.sql",
            "sql.correctness.not-in-subquery",
        ),
        (
            "sql-select-star-row-consumer",
            "order_lookup.sql",
            "sql.schema.select-star",
        ),
    ],
)
def test_directory_fixture_files_yield_the_distractor_hit(stem, hit_file, rule) -> None:
    directory = FIXTURES / stem
    report = _gate_over_directory_files(directory)
    assert report["status"] == "ok"
    assert [(hit["file"], hit["rule"]) for hit in report["hits"]] == [
        (str(directory / hit_file), rule)
    ]


@pytest.mark.parametrize(
    "stem", ["sql-not-in-not-null-migration", "sql-select-star-row-consumer"]
)
def test_directory_path_alone_yields_no_hits(stem) -> None:
    proc = subprocess.run(
        [sys.executable, str(DETECTOR), "--gate", str(FIXTURES / stem)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(proc.stdout)["hits"] == []
