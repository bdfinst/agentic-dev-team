"""Unit tests for scripts/measure_tokens.py (Steps 2.1 and 2.2 of
plans/test-improve-context-loading-strategy.md, issue #1797).

Step 2.1: tokenizer selection (with the fallback path forced independent of
whatever happens to be pip-installed in the running environment),
byte-vs-char parity of the heuristic fallback, per-file measurement,
explicit-path CLI invocation (including a nonexistent path reported as an
error, not a crash), and zero-args auto-discovery against a temp directory
tree mirroring the real glob shape.

Step 2.2: ``--verify`` mode — parsing knowledge/agent-registry.md's
"## Team Agents" and "## Skills Registry" markdown tables and comparing
declared ``~Tokens`` values against measured file sizes. All ``--verify``
tests use fixture markdown tables built in this file — never the live
``agent-registry.md`` — so they stay stable as future PRs edit the real
registry.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "measure_tokens.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_tokens", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec: measure_tokens.py's VerifyRow is a
    # @dataclass under `from __future__ import annotations`, and dataclass
    # field processing resolves string annotations via
    # sys.modules[cls.__module__] — without this registration that lookup
    # returns None and raises AttributeError at class-definition time.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mt = _load()


def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# detect_tokenizer
# ---------------------------------------------------------------------------


def test_detect_tokenizer_falls_back_to_heuristic_when_tiktoken_unimportable(monkeypatch):
    # Force ImportError regardless of whether tiktoken happens to be
    # pip-installed in this environment — sys.modules[name] = None makes
    # `import tiktoken` raise ImportError deterministically.
    monkeypatch.setitem(sys.modules, "tiktoken", None)

    tokenizer, note = mt.detect_tokenizer()

    assert tokenizer == "heuristic"
    assert "heuristic" in note.lower()


def test_detect_tokenizer_uses_tiktoken_when_importable(monkeypatch):
    import types

    fake_tiktoken = types.ModuleType("tiktoken")
    monkeypatch.setitem(sys.modules, "tiktoken", fake_tiktoken)

    tokenizer, note = mt.detect_tokenizer()

    assert tokenizer == "tiktoken"
    assert "tiktoken" in note.lower()


# ---------------------------------------------------------------------------
# count_tokens — byte-vs-char parity, known byte count
# ---------------------------------------------------------------------------


def test_count_tokens_heuristic_uses_utf8_byte_length_not_char_length(tmp_path):
    # "café" x 50 has non-ASCII content where byte length != char length
    # (each "é" is 2 bytes in UTF-8, 1 char in Python str).
    text = "café " * 50
    f = tmp_path / "nonascii.md"
    f.write_text(text, encoding="utf-8")

    byte_based = len(text.encode("utf-8")) // 4
    char_based = len(text) // 4
    assert byte_based != char_based, "fixture must actually exercise byte/char divergence"

    tokens = mt.count_tokens(f, "heuristic")

    assert tokens == byte_based
    assert tokens != char_based


def test_count_tokens_heuristic_known_byte_count(tmp_path):
    f = tmp_path / "known.md"
    content = "x" * 400  # 400 ASCII bytes
    f.write_text(content, encoding="utf-8")

    assert mt.count_tokens(f, "heuristic") == 100  # 400 / 4


# ---------------------------------------------------------------------------
# Explicit-path CLI invocation
# ---------------------------------------------------------------------------


def test_bare_mode_measures_multiple_explicit_paths(tmp_path):
    f1 = tmp_path / "a.md"
    f1.write_text("a" * 40, encoding="utf-8")
    f2 = tmp_path / "b.md"
    f2.write_text("b" * 80, encoding="utf-8")

    result = _run_cli([str(f1), str(f2)])

    assert result.returncode == 0
    assert str(f1) in result.stdout
    assert str(f2) in result.stdout
    assert "TOTAL" in result.stdout


def test_bare_mode_explicit_nonexistent_path_reports_error_not_crash(tmp_path):
    missing = tmp_path / "does-not-exist.md"

    result = _run_cli([str(missing)])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert str(missing) in result.stdout or str(missing) in result.stderr


# ---------------------------------------------------------------------------
# discover_budget_targets — zero-args auto-discovery
# ---------------------------------------------------------------------------


def _build_fixture_repo(tmp_path: Path) -> Path:
    """Build a temp directory tree mirroring the real glob shape:
    agents/*.md, skills/*/SKILL.md, knowledge/*.md, plus the two fixed
    files. No prompts/ dir (matching the real repo today).
    """
    plugin_root = tmp_path / "plugins" / "dev-team"

    agents_dir = plugin_root / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "architect.md").write_text("agent a", encoding="utf-8")
    (agents_dir / "orchestrator.md").write_text("agent b", encoding="utf-8")

    skills_dir = plugin_root / "skills"
    (skills_dir / "code-review").mkdir(parents=True)
    (skills_dir / "code-review" / "SKILL.md").write_text("skill a", encoding="utf-8")
    (skills_dir / "build").mkdir(parents=True)
    (skills_dir / "build" / "SKILL.md").write_text("skill b", encoding="utf-8")
    # A non-SKILL.md file under skills/ must not be picked up.
    (skills_dir / "build" / "references.md").write_text("not a skill entry", encoding="utf-8")

    knowledge_dir = plugin_root / "knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "agent-registry.md").write_text("registry", encoding="utf-8")
    (knowledge_dir / "other-knowledge.md").write_text("other", encoding="utf-8")

    (plugin_root / "CLAUDE.md").write_text("claude md", encoding="utf-8")

    return tmp_path


def test_discover_budget_targets_matches_real_glob_shape(tmp_path):
    fixture_root = _build_fixture_repo(tmp_path)

    targets = mt.discover_budget_targets(fixture_root)

    expected = sorted(
        {
            "plugins/dev-team/CLAUDE.md",
            "plugins/dev-team/knowledge/agent-registry.md",
            "plugins/dev-team/agents/architect.md",
            "plugins/dev-team/agents/orchestrator.md",
            "plugins/dev-team/skills/code-review/SKILL.md",
            "plugins/dev-team/skills/build/SKILL.md",
            "plugins/dev-team/knowledge/other-knowledge.md",
        }
    )

    assert targets == expected
    # The non-SKILL.md sibling file must never appear.
    assert "plugins/dev-team/skills/build/references.md" not in targets


def test_discover_budget_targets_includes_prompts_dir_when_present(tmp_path):
    fixture_root = _build_fixture_repo(tmp_path)
    prompts_dir = fixture_root / "plugins" / "dev-team" / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "reviewer.md").write_text("prompt", encoding="utf-8")

    targets = mt.discover_budget_targets(fixture_root)

    assert "plugins/dev-team/prompts/reviewer.md" in targets


def test_discover_budget_targets_empty_glob_when_prompts_dir_absent(tmp_path):
    fixture_root = _build_fixture_repo(tmp_path)
    assert not (fixture_root / "plugins" / "dev-team" / "prompts").exists()

    targets = mt.discover_budget_targets(fixture_root)

    assert not any("/prompts/" in t for t in targets)


def test_zero_args_cli_measures_repo_default_file_set():
    # Integration smoke test against the real repo (the script always
    # resolves REPO_ROOT from its own on-disk location, so a temp-fixture
    # tree can't be substituted at the CLI level — see discover_budget_targets
    # unit tests above for the exact-set assertions against a fixture tree).
    result = _run_cli([])

    assert result.returncode == 0
    assert "TOTAL" in result.stdout
    assert "plugins/dev-team/CLAUDE.md" in result.stdout
    assert "plugins/dev-team/knowledge/agent-registry.md" in result.stdout


# ---------------------------------------------------------------------------
# --verify mode (Step 2.2) — fixture markdown tables only, never the live
# knowledge/agent-registry.md (asserting against the real file would go
# flaky as future PRs edit it).
# ---------------------------------------------------------------------------


def _build_registry_md(
    *,
    team_rows: str,
    skills_rows: str,
    include_team: bool = True,
    include_skills: bool = True,
) -> str:
    """Build a fixture registry markdown document with the same table shape
    as the real ``knowledge/agent-registry.md``: a "## Team Agents" table,
    an unrelated "## Review Agents" heading in between (to prove block
    extraction stops at the next ``##`` heading rather than running to EOF),
    a "## Skills Registry" table, and a trailing "## Knowledge Files"
    heading. ``team_rows``/``skills_rows`` are pre-formatted pipe-delimited
    data-row lines (no header/separator — those are added here).
    """
    lines = ["# Fixture Agent & Skill Registry", ""]
    if include_team:
        lines += [
            "## Team Agents",
            "",
            "| Agent | File | ~Tokens | Primary Focus |",
            "| ------- | ------ | --------- | --------------- |",
        ]
        lines += [line for line in team_rows.splitlines() if line]
        lines += [""]
    lines += ["## Review Agents", "", "(not consulted by --verify)", ""]
    if include_skills:
        lines += [
            "## Skills Registry",
            "",
            "| Skill | File | ~Tokens | Used By |",
            "| ------- | ------ | --------- | --------- |",
        ]
        lines += [line for line in skills_rows.splitlines() if line]
        lines += [""]
    lines += ["## Knowledge Files", "", "(not consulted by --verify)"]
    return "\n".join(lines)


def test_verify_exceptions_module_constant_defaults_empty():
    assert mt.VERIFY_EXCEPTIONS == {}


def test_extract_table_block_stops_at_next_heading():
    text = (
        "## Team Agents\n"
        "\n"
        "row1\n"
        "row2\n"
        "## Review Agents\n"
        "\n"
        "should not be included"
    )

    block = mt.extract_table_block(text, "Team Agents")

    assert "row1" in block
    assert "row2" in block
    assert "should not be included" not in block


def test_extract_table_block_returns_none_when_heading_absent():
    text = "## Something Else\n\nrow1\n"

    assert mt.extract_table_block(text, "Team Agents") is None


def test_verify_clean_pass_exits_zero(tmp_path):
    """Scenario 1: every row within 10% — exits 0."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")  # 100 tokens
    (tmp_path / "skills" / "bar").mkdir(parents=True)
    (tmp_path / "skills" / "bar" / "SKILL.md").write_text("y" * 200, encoding="utf-8")  # 50 tokens

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows="| Foo | `agents/foo.md` | ~100 | desc |",
            skills_rows="| Bar | `skills/bar/SKILL.md` | 50 | desc |",
        ),
        encoding="utf-8",
    )

    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic")

    assert section_errors == []
    assert len(rows) == 2
    assert all(row.status == "ok" for row in rows)
    assert mt.compute_verify_exit_code(rows, section_errors) == 0


def test_verify_single_drifted_row_fails(tmp_path):
    """Scenario 2: a single drifted row fails."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")  # 100 tokens

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows="| Foo | `agents/foo.md` | ~50 | desc |",  # declared 50 vs measured 100
            skills_rows="",
        ),
        encoding="utf-8",
    )

    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic")

    assert section_errors == []
    assert len(rows) == 1
    assert rows[0].status == "deviated"
    assert mt.compute_verify_exit_code(rows, section_errors) == 1


def test_verify_multiple_drifted_rows_all_reported_single_exit(tmp_path):
    """Scenario 3: multiple drifted rows all appear in the report, and the
    run exits non-zero exactly once (a single int, not a per-row exit)."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")  # 100 tokens
    (tmp_path / "agents" / "baz.md").write_text("z" * 800, encoding="utf-8")  # 200 tokens

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows=(
                "| Foo | `agents/foo.md` | ~50 | desc |\n"
                "| Baz | `agents/baz.md` | ~10 | desc |"
            ),
            skills_rows="",
        ),
        encoding="utf-8",
    )

    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic")
    exit_code = mt.compute_verify_exit_code(rows, section_errors)

    deviated_names = {row.name for row in rows if row.status == "deviated"}
    assert deviated_names == {"Foo", "Baz"}
    assert exit_code == 1
    assert isinstance(exit_code, int)


def test_verify_exempted_row_via_exceptions_param_does_not_fail(tmp_path):
    """Scenario 4: an exceptions-listed row doesn't fail despite drift.
    verify_registry accepts an exceptions dict as a parameter rather than
    always reading the module global, so this test injects one directly.
    """
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")  # 100 tokens

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows="| Foo | `agents/foo.md` | ~50 | desc |",  # would deviate
            skills_rows="",
        ),
        encoding="utf-8",
    )

    exceptions = {"agents/foo.md": "intentionally stale — refreshed in a follow-up"}
    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic", exceptions)

    assert rows[0].status == "exempt"
    assert rows[0].reason == exceptions["agents/foo.md"]
    assert mt.compute_verify_exit_code(rows, section_errors) == 0


def test_verify_skips_empty_file_cell_summary_row(tmp_path):
    """Scenario 5: the '**All team agents**'-style empty-File-cell summary
    row is skipped, not misparsed."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows=(
                "| Foo | `agents/foo.md` | ~100 | desc |\n"
                "| **All team agents** | | **~100** | |"
            ),
            skills_rows="",
        ),
        encoding="utf-8",
    )

    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic")

    assert section_errors == []
    assert len(rows) == 1
    assert rows[0].name == "Foo"


def test_verify_missing_file_reported_as_error_not_crash(tmp_path):
    """Scenario 6: a row whose file doesn't exist on disk is reported as an
    error, not a crash, and contributes to a non-zero exit."""
    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows="| Ghost | `agents/ghost.md` | ~100 | desc |",
            skills_rows="",
        ),
        encoding="utf-8",
    )

    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic")

    assert rows[0].status == "missing_file"
    assert rows[0].measured_n is None
    assert mt.compute_verify_exit_code(rows, section_errors) == 1


def test_verify_parses_comma_formatted_declared_value():
    """Scenario 7: `~1,050` compares against 1050, not 1."""
    assert mt.parse_declared_value("~1,050") == 1050


def test_verify_comma_formatted_declared_value_used_in_comparison(tmp_path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 4200, encoding="utf-8")  # 1050 tokens

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows="| Foo | `agents/foo.md` | ~1,050 | desc |",
            skills_rows="",
        ),
        encoding="utf-8",
    )

    rows, _section_errors = mt.verify_registry(tmp_path, registry, "heuristic")

    assert rows[0].declared_n == 1050
    assert rows[0].status == "ok"


def test_verify_bare_integer_declared_value_parses_same_as_tilde():
    """Scenario 8: `320` (no tilde) parses the same as `~320`."""
    assert mt.parse_declared_value("320") == mt.parse_declared_value("~320") == 320


def test_verify_never_reads_claude_md_sources_from_registry_alone(tmp_path, monkeypatch):
    """Scenario 9 (the actual regression case): a fixture CLAUDE.md with no
    Baseline Budget section sits alongside a populated fixture registry.
    --verify must never read the CLAUDE.md fixture at all and must succeed
    from the registry alone.
    """
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# Fixture CLAUDE.md\n\nNo Baseline Budget section here at all.\n",
        encoding="utf-8",
    )

    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")  # 100 tokens

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows="| Foo | `agents/foo.md` | ~100 | desc |",
            skills_rows="",
        ),
        encoding="utf-8",
    )

    real_read_text = Path.read_text

    def _guarded_read_text(self, *args, **kwargs):
        if self.name == "CLAUDE.md":
            raise AssertionError(f"--verify must never read {self}")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _guarded_read_text)

    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic")

    assert section_errors == []
    assert rows[0].status == "ok"
    assert mt.compute_verify_exit_code(rows, section_errors) == 0


@pytest.mark.parametrize(
    "include_team, include_skills, expected_missing_headings",
    [
        (False, True, ["## Team Agents"]),
        (True, False, ["## Skills Registry"]),
        (False, False, ["## Team Agents", "## Skills Registry"]),
    ],
    ids=["team-missing", "skills-missing", "both-missing"],
)
def test_verify_missing_heading_reported_as_clear_error_not_crash(
    tmp_path, include_team, include_skills, expected_missing_headings
):
    """Scenario 10 (Scenario Outline): a fixture registry missing
    '## Team Agents' only, one missing '## Skills Registry' only, and one
    missing both — each reported as a clear "section not found" error, not
    a stack trace, with a non-zero exit.
    """
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")
    (tmp_path / "skills" / "bar").mkdir(parents=True)
    (tmp_path / "skills" / "bar" / "SKILL.md").write_text("y" * 200, encoding="utf-8")

    registry = tmp_path / "agent-registry.md"
    registry.write_text(
        _build_registry_md(
            team_rows="| Foo | `agents/foo.md` | ~100 | desc |",
            skills_rows="| Bar | `skills/bar/SKILL.md` | 50 | desc |",
            include_team=include_team,
            include_skills=include_skills,
        ),
        encoding="utf-8",
    )

    rows, section_errors = mt.verify_registry(tmp_path, registry, "heuristic")

    for heading in expected_missing_headings:
        assert any(heading in err for err in section_errors), section_errors
    assert "Traceback" not in "".join(section_errors)
    assert mt.compute_verify_exit_code(rows, section_errors) == 1


def test_print_verify_report_includes_every_row_and_section_errors(tmp_path, capsys):
    """The report prints every row (including deviated/missing) and every
    section error — nothing is silently dropped from the printed table."""
    rows = [
        mt.VerifyRow("Team Agents", "Foo", "agents/foo.md", 50, 100, 100.0, "deviated"),
        mt.VerifyRow("Team Agents", "Bar", "agents/bar.md", 10, None, None, "missing_file"),
    ]
    section_errors = ["section not found: ## Skills Registry"]

    mt.print_verify_report(tmp_path / "agent-registry.md", "heuristic note", rows, section_errors)

    out = capsys.readouterr().out
    assert "Foo" in out
    assert "Bar" in out
    assert "DEVIATED" in out
    assert "MISSING_FILE" in out
    assert "section not found: ## Skills Registry" in out


def test_verify_cli_flag_dispatches_to_verify_mode(tmp_path, monkeypatch, capsys):
    """Wiring test: `--verify` dispatches main() to the verify path instead
    of the bare-mode path, against a fixture repo root (never the live
    plugin tree)."""
    fixture_plugin_root = tmp_path / "plugins" / "dev-team"
    (fixture_plugin_root / "agents").mkdir(parents=True)
    (fixture_plugin_root / "agents" / "foo.md").write_text("x" * 400, encoding="utf-8")

    registry_dir = fixture_plugin_root / "knowledge"
    registry_dir.mkdir(parents=True)
    (registry_dir / "agent-registry.md").write_text(
        _build_registry_md(
            team_rows="| Foo | `agents/foo.md` | ~100 | desc |",
            skills_rows="",
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mt, "REPO_ROOT", tmp_path)

    exit_code = mt.main(["--verify"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "--verify output" in out
    assert "Team Agents" in out
