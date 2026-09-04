"""Unit tests for skills/code-review/scripts/change_size.py (#1339).

Covers the deterministic change-size gate: a small changeset (few files, few
added lines) outside the review/gate machinery qualifies for a narrowed
fast-path agent panel; anything larger, unparseable, or touching the gate
machinery itself keeps the full panel. Fail-safe: unknown = does not qualify.
"""

from __future__ import annotations

import json
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import change_shape
import change_size


class TestParseNumstat:
    def test_normal_lines_sum_added_only(self):
        result = change_size.parse_numstat(["3\t1\tfoo.py", "5\t0\tbar.py"])
        assert result.file_count == 2
        assert result.added_lines == 8
        assert result.ok is True
        assert result.files == ("foo.py", "bar.py")

    def test_deleted_lines_are_ignored(self):
        # issue #1331's fix: ~1 added line, 97 deleted (a dead file removal).
        result = change_size.parse_numstat(["1\t2\tregistry.md", "0\t95\tdead.md"])
        assert result.added_lines == 1
        assert result.file_count == 2
        assert result.ok is True

    def test_binary_marker_disqualifies(self):
        result = change_size.parse_numstat(["-\t-\timage.png"])
        assert result.ok is False

    def test_malformed_line_disqualifies(self):
        result = change_size.parse_numstat(["not-a-numstat-line"])
        assert result.ok is False

    def test_non_numeric_field_disqualifies(self):
        result = change_size.parse_numstat(["abc\t1\tfoo.py"])
        assert result.ok is False

    def test_empty_input(self):
        result = change_size.parse_numstat([])
        assert result.file_count == 0
        assert result.added_lines == 0
        assert result.ok is True

    def test_blank_lines_ignored(self):
        result = change_size.parse_numstat(["", "  ", "1\t0\tfoo.py"])
        assert result.file_count == 1
        assert result.added_lines == 1


class TestIsGateMachinery:
    def test_hooks_path_is_gate_machinery(self):
        assert change_size.is_gate_machinery("hooks/pre_commit_review.py") is True
        assert change_size.is_gate_machinery("hooks/lib/review_gate_hash.py") is True

    def test_code_review_skill_is_gate_machinery(self):
        assert change_size.is_gate_machinery("skills/code-review/SKILL.md") is True
        assert (
            change_size.is_gate_machinery(
                "skills/code-review/scripts/change_size.py"
            )
            is True
        )

    def test_unrelated_paths_are_not_gate_machinery(self):
        for path in [
            "knowledge/agent-registry.md",
            "agents/plan-reviewer.md",
            "skills/plan/SKILL.md",
            "src/app.py",
            "README.md",
        ]:
            assert change_size.is_gate_machinery(path) is False, path


class TestQualifiesForFastPath:
    def test_small_non_gate_changeset_qualifies(self):
        # issue #1331's fix, restated as numstat.
        result = change_size.parse_numstat(
            ["1\t2\tknowledge/agent-registry.md", "0\t95\tprompts/plan-reviewer.md"]
        )
        assert change_size.qualifies_for_fast_path(result) is True

    def test_too_many_files_disqualifies(self):
        lines = [f"1\t0\tfile{i}.py" for i in range(change_size.MAX_FILES + 1)]
        result = change_size.parse_numstat(lines)
        assert change_size.qualifies_for_fast_path(result) is False

    def test_too_many_added_lines_disqualifies(self):
        # issue #1334's fix: 25 files, 537 added lines.
        lines = [f"22\t6\tfile{i}.py" for i in range(25)]
        result = change_size.parse_numstat(lines)
        assert result.added_lines == 550
        assert change_size.qualifies_for_fast_path(result) is False

    def test_exactly_at_threshold_qualifies(self):
        lines = [f"{change_size.MAX_ADDED_LINES // change_size.MAX_FILES}\t0\tf{i}.py"
                  for i in range(change_size.MAX_FILES)]
        result = change_size.parse_numstat(lines)
        assert result.file_count == change_size.MAX_FILES
        assert change_size.qualifies_for_fast_path(result) is True

    def test_one_line_over_threshold_disqualifies(self):
        result = change_size.parse_numstat(
            [f"{change_size.MAX_ADDED_LINES + 1}\t0\tfoo.py"]
        )
        assert change_size.qualifies_for_fast_path(result) is False

    def test_gate_machinery_file_disqualifies_even_when_tiny(self):
        result = change_size.parse_numstat(["1\t0\thooks/pre_commit_review.py"])
        assert change_size.qualifies_for_fast_path(result) is False

    def test_gate_machinery_among_otherwise_small_files_disqualifies(self):
        result = change_size.parse_numstat(
            ["1\t0\tREADME.md", "1\t0\tskills/code-review/SKILL.md"]
        )
        assert change_size.qualifies_for_fast_path(result) is False

    def test_unparseable_numstat_disqualifies(self):
        result = change_size.parse_numstat(["garbage"])
        assert change_size.qualifies_for_fast_path(result) is False

    def test_empty_changeset_does_not_qualify(self):
        result = change_size.parse_numstat([])
        assert change_size.qualifies_for_fast_path(result) is False


class TestEvaluate:
    def test_qualifying_scope_reports_keep_agents(self):
        out = change_size.evaluate(["1\t2\tregistry.md"])
        assert out["qualifiesForFastPath"] is True
        assert out["keepAgents"] == change_size.FAST_PATH_AGENTS

    def test_disqualifying_scope_reports_empty_keep_agents(self):
        out = change_size.evaluate(["600\t0\tbig.py"])
        assert out["qualifiesForFastPath"] is False
        assert out["keepAgents"] == []


class TestCli:
    def test_cli_qualifying_scope(self, capsys):
        rc = change_size.main(["--numstat", "1\t0\tfoo.md"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["qualifiesForFastPath"] is True
        assert out["filesChanged"] == 1
        assert out["addedLines"] == 1

    def test_cli_numstat_from_stdin(self, capsys, monkeypatch):
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO("1\t0\tfoo.md\n2\t0\tbar.md\n"))
        rc = change_size.main(["--numstat-from", "-"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["filesChanged"] == 2
        assert out["addedLines"] == 3
        assert out["qualifiesForFastPath"] is True

    def test_cli_disqualifying_scope(self, capsys):
        rc = change_size.main(["--numstat", "1\t0\thooks/pre_commit_review.py"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["qualifiesForFastPath"] is False


class TestComposesWithChangeShapeGate:
    """AC6: the size gate must never re-add an agent the shape gate already
    dropped — proving the "intersection, never re-add" composition rule at
    the unit level, not just in SKILL.md prose.
    """

    def test_never_readds_agent_shape_gate_already_dropped(self):
        files = ["README.md"]  # doc-only, small, not gate machinery.

        skipped_by_shape = set(change_shape.lenses_to_skip(files))
        assert "correctness-review" in skipped_by_shape  # sanity: shape drops it
        # README.md is also prose-only (#2104), so the shape gate drops
        # security-review too — its own `## Skip` clause already self-reports
        # skip on a documentation-only target.
        assert "security-review" in skipped_by_shape

        size_result = change_size.parse_numstat(["1\t0\tREADME.md"])
        assert change_size.qualifies_for_fast_path(size_result) is True
        kept_by_size = set(change_size.FAST_PATH_AGENTS)
        assert "correctness-review" in kept_by_size  # size alone would keep it
        assert "security-review" in kept_by_size

        # Composition order (SKILL.md Step 3): apply shape-skip first, then
        # size's keep-list only narrows what's left — it never re-adds.
        full_roster = {
            "security-review", "correctness-review", "spec-compliance-review",
            "doc-review", "performance-review", "structure-review",
        }
        after_shape = full_roster - skipped_by_shape
        final_roster = after_shape & kept_by_size

        assert "correctness-review" not in final_roster
        assert "performance-review" not in final_roster
        assert "structure-review" not in final_roster
        # security-review was dropped by shape above, never re-added by size.
        assert "security-review" not in final_roster
        assert final_roster == {"spec-compliance-review", "doc-review"}
