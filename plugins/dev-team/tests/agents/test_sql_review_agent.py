"""sql-review agent: file structure, registration, and the dispatch gate (#2283).

The dispatch scenarios run the real ``sql_review_roster.py`` and
``select_lenses.py`` as subprocesses. The decision function is also tested
directly for the detector-failure shapes that a healthy detector cannot
produce.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_DIR.parents[1]
SCRIPTS_DIR = PLUGIN_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

import review_roster
import sql_review_roster

AGENT = PLUGIN_DIR / "agents" / "sql-review.md"
KNOWLEDGE = PLUGIN_DIR / "knowledge"
SKILL = PLUGIN_DIR / "skills" / "code-review" / "SKILL.md"
ROSTER_CLI = SCRIPTS_DIR / "sql_review_roster.py"
SELECT_LENSES = SCRIPTS_DIR / "select_lenses.py"
RULE = "sql.schema.positional-insert"


def frontmatter(text: str) -> dict:
    block = text.split("---", 2)[1]
    fields = {}
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z-]+):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


AGENT_TEXT = AGENT.read_text(encoding="utf-8")
FM = frontmatter(AGENT_TEXT)


# --- File structure ----------------------------------------------------------


def test_agent_is_read_only_haiku_review_agent():
    assert FM["name"] == "sql-review"
    assert FM["model"] == "haiku"
    assert FM["color"] == "green"
    assert [t.strip() for t in FM["tools"].split(",")] == ["Read", "Grep", "Glob"]


def test_agent_declares_on_demand_scope_so_the_resolver_skips_it():
    assert re.search(r"^Scope: on-demand$", AGENT_TEXT, re.MULTILINE)


def test_agent_cites_the_output_contract_and_the_catalog():
    assert "knowledge/review-agent-output-contract.md" in AGENT_TEXT
    assert "knowledge/sql-anti-patterns/" in AGENT_TEXT


@pytest.mark.parametrize(
    "phrase",
    [
        "security-review",
        "performance-review",
        "sql-review: ignore",
        "never change it",
        "sql_anti_patterns.py",
    ],
)
def test_agent_body_states_its_boundaries_and_contract(phrase):
    assert phrase.lower() in AGENT_TEXT.lower()


def test_agent_does_not_claim_injection_or_n_plus_one():
    detect = AGENT_TEXT.split("## Detect", 1)[1].split("## Suppression", 1)[0]
    assert "injection" not in detect.lower()
    assert "n+1" not in detect.lower()


# --- Registration ---------------------------------------------------------------


def table_names(path: Path, heading_marker: str) -> list[str]:
    names, active = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            active = heading_marker in line.lower()
        elif active:
            match = re.match(r"^\|\s*`?([a-z][a-z0-9-]*)`?\s*\|", line)
            if match:
                names.append(match.group(1))
    return names


def test_registered_in_the_agent_registry_review_table():
    assert "sql-review" in table_names(KNOWLEDGE / "agent-registry.md", "review agents")


def test_classified_as_a_discovery_lens():
    text = (KNOWLEDGE / "review-lens-classification.md").read_text(encoding="utf-8")
    assert re.search(r"^\| sql-review \| discovery-lens \|", text, re.MULTILINE)


def test_listed_in_the_review_rubric():
    text = (KNOWLEDGE / "review-rubric.md").read_text(encoding="utf-8")
    assert "sql-review" in text


def test_listed_in_agent_info():
    text = (PLUGIN_DIR / "docs" / "agent_info.md").read_text(encoding="utf-8")
    assert "`sql-review`" in text


def test_exempt_from_the_code_intelligence_tool_grant():
    import check_review_agent_mcp_tools

    assert "sql-review" in check_review_agent_mcp_tools.EXEMPT_AGENTS


# --- The /code-review pre-step is documented ---------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "sql_review_roster.py",
        "sql_anti_patterns.py --gate",
        "Scope: on-demand",
        "dispatchFailure",
        "Do not skip the lens and do not report a pass",
        "SQL-shaped fragment",
    ],
)
def test_code_review_skill_documents_the_sql_pre_step(phrase):
    assert phrase in SKILL.read_text(encoding="utf-8")


# --- Dispatch gate: deterministic roster logic ----------------------------------------


def write(root, name, content):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return name


def roster(root, *names):
    proc = subprocess.run(
        [sys.executable, str(ROSTER_CLI), *names],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_changeset_with_sql_dispatches_sql_review_with_the_hits(tmp_path):
    write(tmp_path, "db/seed.sql", "INSERT INTO orders VALUES (1, 'a')\n")
    write(tmp_path, "README.md", "# docs")
    decision = roster(tmp_path, "README.md", "db/seed.sql")
    assert decision["status"] == "ok"
    assert decision["dispatch"] is True
    assert [(h["file"], h["rule"], h["line"]) for h in decision["hits"]] == [
        ("db/seed.sql", RULE, 1)
    ]
    assert review_roster.with_sql_review(["structure-review"], decision) == [
        "sql-review",
        "structure-review",
    ]


@pytest.mark.parametrize(
    "files",
    [("README.md", "src/app.ts"), ("README.md",), ()],
    ids=["docs-and-source", "docs-only", "empty"],
)
def test_changeset_without_sql_does_not_dispatch(tmp_path, files):
    write(tmp_path, "README.md", "INSERT INTO t VALUES (1)")
    write(tmp_path, "src/app.ts", "export const sql = 'SELECT 1'")
    decision = roster(tmp_path, *files)
    assert decision["status"] == "ok"
    assert decision["dispatch"] is False
    assert decision["hits"] == []
    assert review_roster.with_sql_review(["structure-review"], decision) == [
        "structure-review"
    ]


def test_clean_sql_still_dispatches(tmp_path):
    write(tmp_path, "db/clean.sql", "INSERT INTO t (a) VALUES (1);\n")
    decision = roster(tmp_path, "db/clean.sql")
    assert decision["dispatch"] is True
    assert decision["hits"] == []


def test_unreadable_only_sql_file_still_dispatches(tmp_path):
    (tmp_path / "c.sql").write_bytes(b"\xff\xfe")
    decision = roster(tmp_path, "c.sql")
    assert decision["dispatch"] is True
    assert decision["status"] == "ok"
    assert len(decision["errors"]) == 1


def test_resolver_does_not_select_sql_review_for_a_sql_file(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SELECT_LENSES), "--files", "db/seed.sql"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "sql-review" not in json.loads(proc.stdout)["lenses"]


def test_with_sql_review_does_not_duplicate_the_lens():
    decision = {"dispatch": True}
    assert review_roster.with_sql_review(["sql-review", "a"], decision) == [
        "sql-review",
        "a",
    ]


# --- Dispatch gate: detector failure is an error, never a skip or pass -------------------


def gate_payload(**overrides):
    payload = {
        "status": "ok",
        "dispatch": True,
        "hits": [],
        "errors": [],
        "skipped_fragments": {},
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.mark.parametrize(
    ("returncode", "stdout", "needle"),
    [
        (1, "", "exit 1"),
        (2, gate_payload(), "exit 2"),
        (-1, "", "exit -1"),
        (0, "", "not JSON"),
        (0, "Traceback (most recent call last):", "not JSON"),
        (0, "[]", "not a JSON object"),
        (
            0,
            json.dumps({"status": "error", "message": "RuntimeError: boom"}),
            "RuntimeError: boom",
        ),
        (0, json.dumps({"status": "ok"}), "missing gate fields"),
        (0, gate_payload(dispatch="yes"), "missing gate fields"),
        (0, gate_payload(hits=None), "missing gate fields"),
    ],
)
def test_detector_failure_is_a_reported_error(returncode, stdout, needle):
    decision = review_roster.sql_review_decision(returncode, stdout)
    assert decision["status"] == "error"
    assert decision["dispatch"] is False
    assert "sql detector failed" in decision["message"]
    assert needle in decision["message"]
    failure = decision["dispatchFailure"]
    assert failure["agentName"] == "sql-review"
    assert failure["attempts"] == 0
    assert failure["error"] == decision["message"]
    assert review_roster.with_sql_review(["x"], decision) == ["x"]


def test_healthy_gate_has_no_dispatch_failure():
    decision = review_roster.sql_review_decision(0, gate_payload())
    assert decision["status"] == "ok"
    assert decision["dispatchFailure"] is None


def test_a_crashing_detector_surfaces_as_an_error_end_to_end(
    tmp_path, monkeypatch, capsys
):
    crash = tmp_path / "crash.py"
    crash.write_text("raise SystemExit(7)\n")
    monkeypatch.setattr(sql_review_roster, "DETECTOR", crash)
    assert sql_review_roster.main(["db/seed.sql"]) == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["status"] == "error"
    assert "exit 7" in decision["message"]
    assert decision["dispatchFailure"]["agentName"] == "sql-review"


def test_a_missing_detector_surfaces_as_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sql_review_roster, "DETECTOR", tmp_path / "absent.py")
    sql_review_roster.main(["db/seed.sql"])
    decision = json.loads(capsys.readouterr().out)
    assert decision["status"] == "error"
    assert decision["dispatch"] is False
