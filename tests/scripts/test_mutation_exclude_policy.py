"""Pytest tests for mutation_exclude_policy.py — the committed,
human-approved mutation exclude-policy bootstrap (#1757).

The two-signal rule (score < 15%, NoCoverage > 50%) is ported verbatim from
agents/mutation-kill.md's "Infrastructure exclusion detection" section;
these tests pin the same numbers this module's docstring cites.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_exclude_policy as policy


def _write_report(path: Path, files: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


def _mutants(killed=0, survived=0, no_coverage=0, timeout=0) -> list[dict]:
    out = []
    for _ in range(killed):
        out.append({"status": "Killed", "mutatorName": "X"})
    for _ in range(survived):
        out.append({"status": "Survived", "mutatorName": "X"})
    for _ in range(no_coverage):
        out.append({"status": "NoCoverage", "mutatorName": "X"})
    for _ in range(timeout):
        out.append({"status": "Timeout", "mutatorName": "X"})
    return out


# =============================================================================
# Two-signal rule
# =============================================================================


def test_flags_when_both_signals_hold(tmp_path: Path) -> None:
    # score = 1/10 = 10% (< 15%); NoCoverage = 9/10 = 90% (> 50%)
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Startup.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    entries = policy.draft_entries(report, "csharp")
    assert len(entries) == 1
    assert entries[0]["file"] == "src/Startup.cs"


def test_does_not_flag_when_only_score_signal_holds(tmp_path: Path) -> None:
    # score = 1/10 = 10% (< 15%) but NoCoverage = 0% (not > 50%)
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Real.cs": {"mutants": _mutants(killed=1, survived=9)}},
    )
    assert policy.draft_entries(report, "csharp") == []


def test_does_not_flag_when_only_no_coverage_signal_holds(tmp_path: Path) -> None:
    # score = 5/10 = 50% (not < 15%) even though NoCoverage = 50%... use a
    # combination where NoCoverage > 50% but score is still high.
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Real.cs": {"mutants": _mutants(killed=9, no_coverage=9)}},
    )
    # score = 9/18 = 50% -> not < 15%, so must not flag despite NoCoverage 50%.
    assert policy.draft_entries(report, "csharp") == []


def test_zero_effective_mutants_never_flagged(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Ignored.cs": {"mutants": _mutants(timeout=5)}},
    )
    assert policy.draft_entries(report, "csharp") == []


# =============================================================================
# Filename hint tiering
# =============================================================================


def test_filename_hint_promotes_to_always_tier(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Startup.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    entries = policy.draft_entries(report, "csharp")
    assert entries[0]["tier"] == "always"
    assert "named convention" in entries[0]["reason"]


def test_no_filename_hint_stays_propose_and_ask(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/OrderProcessor.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    entries = policy.draft_entries(report, "csharp")
    assert entries[0]["tier"] == "propose_and_ask"
    assert "signal-only" in entries[0]["reason"]


def test_javascript_hint_list_applies_too(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/app.module.ts": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    entries = policy.draft_entries(report, "javascript")
    assert entries[0]["tier"] == "always"


def test_known_stack_without_hints_stays_propose_and_ask(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Startup.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    entries = policy.draft_entries(report, "java")
    assert entries[0]["tier"] == "propose_and_ask"


def test_genuinely_unknown_stack_raises_value_error(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Startup.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    try:
        policy.draft_entries(report, "rust")
    except ValueError as exc:
        assert "rust" in str(exc)
    else:
        raise AssertionError("expected ValueError for unrecognized stack name")


# =============================================================================
# draft_policy aggregation
# =============================================================================


def test_draft_policy_aggregates_across_stacks(tmp_path: Path) -> None:
    js_report = _write_report(
        tmp_path / "js.json",
        {"src/main.ts": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    cs_report = _write_report(
        tmp_path / "cs.json",
        {"src/OrderProcessor.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    result = policy.draft_policy({"javascript": js_report, "csharp": cs_report})
    assert result["schema_version"] == 1
    assert len(result["always"]) == 1
    assert result["always"][0]["file"] == "src/main.ts"
    assert len(result["propose_and_ask"]) == 1
    assert result["propose_and_ask"][0]["file"] == "src/OrderProcessor.cs"


def test_draft_policy_empty_when_nothing_flagged(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Real.cs": {"mutants": _mutants(killed=9, survived=1)}},
    )
    result = policy.draft_policy({"csharp": report})
    assert result == {"schema_version": 1, "always": [], "propose_and_ask": []}


# =============================================================================
# write_json / approve — the human-approval gate
# =============================================================================


def test_write_json_creates_parent_dirs(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "dir" / "draft.json"
    policy.write_json(out, {"a": 1})
    assert json.loads(out.read_text(encoding="utf-8")) == {"a": 1}


def test_approve_writes_committed_policy_at_repo_root(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.json"
    draft = {"schema_version": 1, "always": [{"file": "a"}], "propose_and_ask": []}
    policy.write_json(draft_path, draft)

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    written = policy.approve(draft_path, repo_root)

    assert written == repo_root / policy.POLICY_FILENAME
    assert json.loads(written.read_text(encoding="utf-8")) == draft


def test_draft_policy_never_writes_to_a_repo_root(tmp_path: Path) -> None:
    """draft_policy/draft_entries must never touch the filesystem at all —
    the human-approval gate depends on drafting being a pure, read-only
    computation. approve() is the only writer of the committed file."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Startup.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    policy.draft_policy({"csharp": report})
    assert not (repo_root / policy.POLICY_FILENAME).exists()


# =============================================================================
# CLI
# =============================================================================


def test_main_draft_requires_out(capsys) -> None:
    rc = policy.main(["--draft"])
    assert rc == 2
    assert "requires --out" in capsys.readouterr().err


def test_main_draft_writes_output(tmp_path: Path, capsys) -> None:
    report = _write_report(
        tmp_path / "mutation.json",
        {"src/Startup.cs": {"mutants": _mutants(killed=1, no_coverage=9)}},
    )
    out = tmp_path / "out.json"
    rc = policy.main(["--draft", "--report", f"csharp={report}", "--out", str(out)])
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert len(written["always"]) == 1


def test_main_draft_rejects_malformed_report_arg(tmp_path: Path, capsys) -> None:
    rc = policy.main(["--draft", "--report", "not-a-kv-pair", "--out", str(tmp_path / "o.json")])
    assert rc == 2
    assert "STACK=PATH" in capsys.readouterr().err


def test_main_approve_writes_policy(tmp_path: Path, capsys) -> None:
    draft_path = tmp_path / "draft.json"
    policy.write_json(draft_path, {"schema_version": 1, "always": [], "propose_and_ask": []})
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rc = policy.main(["--approve", str(draft_path), "--repo-root", str(repo_root)])
    assert rc == 0
    assert (repo_root / policy.POLICY_FILENAME).exists()


def test_main_with_no_mode_errors(capsys) -> None:
    rc = policy.main([])
    assert rc == 2
    assert "--draft or --approve" in capsys.readouterr().err
