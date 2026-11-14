"""Unit tests for skills/code-review/scripts/render_tiered_findings.py (#2170).

Covers finding-id derivation (including the ordinal-suffix collision case),
Tier-1 rendering, Tier-2 rendering via `--expand <id>|all`, the unknown-id
failure contract, and the zero-finding clean-pass path.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import render_tiered_findings as rtf


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Each CLI run writes its render row under a throwaway project, never the repo's own metrics."""
    monkeypatch.chdir(tmp_path)


_SCRIPT = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "code-review"
    / "scripts"
    / "render_tiered_findings.py"
)


def _finding(**overrides) -> dict:
    base = {
        "agent": "structure-review",
        "file": "src/auth/login.ts",
        "line": 42,
        "severity": "warning",
        "confidence": "medium",
        "message": "God object: AuthController handles login, registration, and password reset.",
        "suggestedFix": "Split into LoginController, RegistrationController, and PasswordResetController",
    }
    base.update(overrides)
    return base


class TestFirstSentence:
    def test_splits_at_first_terminator(self):
        assert rtf.first_sentence("First. Second.") == "First."

    def test_no_terminator_returns_whole_message(self):
        assert rtf.first_sentence("No terminator here") == "No terminator here"

    def test_empty_message(self):
        assert rtf.first_sentence("") == ""
        assert rtf.first_sentence(None) == ""


class TestBaseId:
    def test_id_without_category(self):
        finding = _finding()
        assert rtf.base_id(finding) == "structure-review:src/auth/login.ts:42:warning"

    def test_id_with_category(self):
        finding = _finding(category="god-object")
        assert (
            rtf.base_id(finding)
            == "structure-review:src/auth/login.ts:42:warning:god-object"
        )

    def test_empty_category_excluded(self):
        finding = _finding(category="")
        assert rtf.base_id(finding) == "structure-review:src/auth/login.ts:42:warning"

    def test_agentname_fallback(self):
        finding = _finding()
        del finding["agent"]
        finding["agentName"] = "structure-review"
        assert rtf.base_id(finding) == "structure-review:src/auth/login.ts:42:warning"

    def test_smell_field_used_as_taxonomy_tag_when_no_category(self):
        """test-smell-review carries its taxonomy in `smell`, not `category`
        (knowledge/review-agent-output-contract.md) — base_id must mirror
        finding_signature.py's signature() fallback chain so this finding
        gets a semantically-named id segment, not a bare ordinal."""
        finding = _finding(agent="test-smell-review", smell="eager-test")
        assert (
            rtf.base_id(finding)
            == "test-smell-review:src/auth/login.ts:42:warning:eager-test"
        )


class TestComputeIds:
    def test_unique_findings_keep_base_ids(self):
        findings = [_finding(), _finding(file="other.ts", line=7)]
        ids = rtf.compute_ids(findings)
        assert ids == [
            "structure-review:src/auth/login.ts:42:warning",
            "structure-review:other.ts:7:warning",
        ]

    def test_colliding_base_ids_get_ordinal_suffixes_in_list_order(self):
        findings = [
            _finding(message="First distinct message."),
            _finding(message="Second distinct message."),
        ]
        ids = rtf.compute_ids(findings)
        assert ids == [
            "structure-review:src/auth/login.ts:42:warning#0",
            "structure-review:src/auth/login.ts:42:warning#1",
        ]

    def test_three_way_collision_gets_three_ordinals(self):
        findings = [_finding(message=f"Message {i}.") for i in range(3)]
        ids = rtf.compute_ids(findings)
        assert ids == [
            "structure-review:src/auth/login.ts:42:warning#0",
            "structure-review:src/auth/login.ts:42:warning#1",
            "structure-review:src/auth/login.ts:42:warning#2",
        ]


class TestRenderTier1Report:
    def test_multi_finding_render(self):
        findings = [
            _finding(),
            _finding(
                file="src/api/handler.ts",
                line=15,
                agent="security-review",
                severity="error",
                confidence="high",
                message="SQL injection via unsanitized query parameter.",
            ),
        ]
        ids = rtf.compute_ids(findings)
        report = rtf.render_tier1_report(findings, ids)
        lines = report.splitlines()

        assert lines[0] == (
            "src/auth/login.ts:42 [structure-review] warning/medium — "
            "God object: AuthController handles login, registration, and password reset. "
            "(structure-review:src/auth/login.ts:42:warning)"
        )
        assert lines[1] == (
            "src/api/handler.ts:15 [security-review] error/high — "
            "SQL injection via unsanitized query parameter. "
            "(security-review:src/api/handler.ts:15:error)"
        )
        assert lines[2] == rtf.EXPAND_HINT
        assert len(lines) == 3

    def test_zero_findings_renders_clean_pass_with_no_hint(self):
        report = rtf.render_tier1_report([], [])
        assert report == rtf.CLEAN_PASS_SUMMARY
        assert rtf.EXPAND_HINT not in report


class TestRenderExpand:
    def test_expand_one_renders_only_the_first_findings_tier2_content(self):
        findings = [
            _finding(message="First distinct message.", suggestedFix="Fix A"),
            _finding(message="Second distinct message.", suggestedFix="Fix B"),
        ]
        ids = rtf.compute_ids(findings)

        block = rtf.render_expand_one(findings, ids, ids[0])
        assert "First distinct message." in block
        assert "Fix A" in block
        assert "Second distinct message." not in block
        assert "Fix B" not in block

    def test_expand_one_renders_only_the_second_findings_tier2_content(self):
        findings = [
            _finding(message="First distinct message.", suggestedFix="Fix A"),
            _finding(message="Second distinct message.", suggestedFix="Fix B"),
        ]
        ids = rtf.compute_ids(findings)

        block_other = rtf.render_expand_one(findings, ids, ids[1])
        assert "Second distinct message." in block_other
        assert "Fix B" in block_other
        assert "First distinct message." not in block_other
        assert "Fix A" not in block_other

    def test_expand_block_omits_suggested_fix_line_when_absent(self):
        finding = _finding()
        del finding["suggestedFix"]
        ids = rtf.compute_ids([finding])
        block = rtf.render_expand_one([finding], ids, ids[0])
        assert "Suggested fix:" not in block

    def test_expand_block_omits_suggested_fix_line_when_empty_string(self):
        finding = _finding(suggestedFix="")
        ids = rtf.compute_ids([finding])
        block = rtf.render_expand_one([finding], ids, ids[0])
        assert "Suggested fix:" not in block

    def test_expand_all_renders_every_findings_tier2_content(self):
        findings = [
            _finding(message="First distinct message.", suggestedFix="Fix A"),
            _finding(message="Second distinct message.", suggestedFix="Fix B"),
        ]
        ids = rtf.compute_ids(findings)
        report = rtf.render_tier2_report(findings, ids)
        assert "First distinct message." in report
        assert "Fix A" in report
        assert "Second distinct message." in report
        assert "Fix B" in report

    def test_expand_unknown_id_returns_none(self):
        findings = [_finding()]
        ids = rtf.compute_ids(findings)
        assert rtf.render_expand_one(findings, ids, "no-such-id") is None


_SESSION_ENV = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")


def _run(*args, input_text=None, cwd=None, session=None, env_overrides=None):
    """Run the CLI with only the session variables under test set. The
    autouse fixture puts the working directory in ``tmp_path``, so rows never
    land in the checkout's own metrics."""
    env = {k: v for k, v in os.environ.items() if k not in _SESSION_ENV}
    if session is not None:
        env["CLAUDE_CODE_SESSION_ID"] = session
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def _size_rows(base: Path) -> list[dict]:
    log = base / ".claude" / "metrics" / "review-report-sizes.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _render_rows(base) -> list[dict]:
    log = base / ".claude" / "metrics" / "tiered-renders.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


class TestRenderLog:
    """Each successful render of a non-empty report appends one row, so the
    expand rate has both its numerator and its denominator."""

    def test_plain_render_logs_an_unexpanded_row_with_the_session_id(self, tmp_path):
        findings = [_finding(), _finding(line=7)]
        r = _run(input_text=json.dumps(findings), session="sess-1")
        assert r.returncode == 0
        (row,) = _render_rows(tmp_path)
        assert row["expand"] == "none"
        assert row["findings"] == 2
        assert row["session_id"] == "sess-1"
        assert {"ts", "plugin_version", "report"} <= row.keys()

    def test_claude_session_id_alone_sets_the_session_id(self, tmp_path):
        _run(input_text=json.dumps([_finding()]), env_overrides={"CLAUDE_SESSION_ID": "legacy"})
        (row,) = _render_rows(tmp_path)
        assert row["session_id"] == "legacy"

    def test_claude_code_session_id_wins_when_both_are_set(self, tmp_path):
        _run(
            input_text=json.dumps([_finding()]),
            env_overrides={"CLAUDE_CODE_SESSION_ID": "current", "CLAUDE_SESSION_ID": "legacy"},
        )
        (row,) = _render_rows(tmp_path)
        assert row["session_id"] == "current"

    def test_an_empty_claude_code_session_id_falls_back_to_claude_session_id(self, tmp_path):
        _run(
            input_text=json.dumps([_finding()]),
            env_overrides={"CLAUDE_CODE_SESSION_ID": "", "CLAUDE_SESSION_ID": "x"},
        )
        (row,) = _render_rows(tmp_path)
        assert row["session_id"] == "x"

    def test_expand_one_logs_an_expanded_row(self, tmp_path):
        findings = [_finding()]
        ids = rtf.compute_ids(findings)
        _run("--expand", ids[0], input_text=json.dumps(findings), session="s")
        (row,) = _render_rows(tmp_path)
        assert row["expand"] == "one"

    def test_expand_all_logs_an_expanded_row(self, tmp_path):
        _run("--expand", "all", input_text=json.dumps([_finding()]), session="s")
        (row,) = _render_rows(tmp_path)
        assert row["expand"] == "all"

    def test_renders_of_the_same_report_share_a_report_key(self, tmp_path):
        findings = [_finding()]
        ids = rtf.compute_ids(findings)
        _run(input_text=json.dumps(findings), session="s")
        _run("--expand", ids[0], input_text=json.dumps(findings), session="s")
        _run(input_text=json.dumps([_finding(line=7)]), session="s")
        first, expanded, other = _render_rows(tmp_path)
        assert first["report"] == expanded["report"] != other["report"]

    def test_row_carries_only_its_fields_and_a_digest_report_key(self, tmp_path):
        _run(input_text=json.dumps([_finding()]), session="s")
        (row,) = _render_rows(tmp_path)
        assert row.keys() == {"ts", "plugin_version", "session_id", "report", "findings", "expand"}
        assert re.fullmatch(r"[0-9a-f]{12}", row["report"])

    def test_clean_pass_logs_nothing(self, tmp_path):
        r = _run(input_text=json.dumps([]), session="s")
        assert r.returncode == 0
        assert r.stdout.strip() == rtf.CLEAN_PASS_SUMMARY
        assert _render_rows(tmp_path) == []

    def test_unknown_expand_id_logs_nothing(self, tmp_path):
        r = _run("--expand", "no-such-id", input_text=json.dumps([_finding()]), session="s")
        assert r.returncode == 1
        assert "finding-id not found" in r.stderr
        assert _render_rows(tmp_path) == []

    def test_row_omits_session_id_when_none_is_set(self, tmp_path):
        _run(input_text=json.dumps([_finding()]))
        (row,) = _render_rows(tmp_path)
        assert "session_id" not in row

    def test_unwritable_metrics_location_keeps_output_and_exit_code(self, tmp_path):
        (tmp_path / ".claude").write_text("not a directory")
        r = _run(input_text=json.dumps([_finding()]), session="s")
        assert r.returncode == 0
        assert rtf.EXPAND_HINT in r.stdout


class TestCli:
    def test_cli_default_renders_tier1(self):
        findings = [_finding()]
        r = _run(input_text=json.dumps(findings))
        assert r.returncode == 0
        assert "structure-review:src/auth/login.ts:42:warning" in r.stdout
        assert rtf.EXPAND_HINT in r.stdout

    def test_cli_zero_findings_renders_clean_pass(self):
        r = _run(input_text=json.dumps([]))
        assert r.returncode == 0
        assert r.stdout.strip() == rtf.CLEAN_PASS_SUMMARY
        assert rtf.EXPAND_HINT not in r.stdout

    def test_cli_expand_known_id_exits_zero_with_tier2_content(self):
        findings = [_finding()]
        ids = rtf.compute_ids(findings)
        r = _run("--expand", ids[0], input_text=json.dumps(findings))
        assert r.returncode == 0
        assert "Split into LoginController" in r.stdout

    def test_cli_expand_known_id_also_includes_tier1_report(self):
        """--expand <id> appends Tier-2 AFTER the Tier-1 report — it does not
        replace it (skills/code-review/SKILL.md step 7, output-format.md)."""
        findings = [_finding()]
        ids = rtf.compute_ids(findings)
        r = _run("--expand", ids[0], input_text=json.dumps(findings))
        assert r.returncode == 0
        assert ids[0] in r.stdout.splitlines()[0]
        assert rtf.EXPAND_HINT in r.stdout

    def test_cli_expand_unknown_id_fails_clearly(self):
        findings = [_finding()]
        r = _run("--expand", "no-such-id", input_text=json.dumps(findings))
        assert r.returncode != 0
        assert "no-such-id" in r.stderr
        assert "not found" in r.stderr.lower()

    def test_cli_expand_all(self):
        findings = [
            _finding(message="First distinct message.", suggestedFix="Fix A"),
            _finding(message="Second distinct message.", suggestedFix="Fix B"),
        ]
        r = _run("--expand", "all", input_text=json.dumps(findings))
        assert r.returncode == 0
        assert "First distinct message." in r.stdout
        assert "Second distinct message." in r.stdout

    def test_cli_expand_all_also_includes_tier1_report(self):
        """--expand all appends Tier-2 AFTER the Tier-1 report — it does not
        replace it (skills/code-review/SKILL.md step 7, output-format.md)."""
        findings = [
            _finding(message="First distinct message.", suggestedFix="Fix A"),
            _finding(message="Second distinct message.", suggestedFix="Fix B"),
        ]
        ids = rtf.compute_ids(findings)
        r = _run("--expand", "all", input_text=json.dumps(findings))
        assert r.returncode == 0
        assert ids[0] in r.stdout.splitlines()[0]
        assert ids[1] in r.stdout.splitlines()[1]
        assert rtf.EXPAND_HINT in r.stdout

    def test_cli_findings_from_file(self, tmp_path):
        findings_file = tmp_path / "findings.json"
        findings_file.write_text(json.dumps([_finding()]))
        r = _run("--findings", str(findings_file))
        assert r.returncode == 0
        assert "structure-review:src/auth/login.ts:42:warning" in r.stdout

    def test_cli_accepts_dict_wrapped_findings_shape(self):
        """`_load_findings` accepts both a bare list and a `{"findings":
        [...]}` dict-wrapped shape — the dict-wrapped shape must render
        identically to the equivalent bare list."""
        findings = [_finding()]
        wrapped = {"findings": findings}
        r = _run(input_text=json.dumps(wrapped))
        r_bare = _run(input_text=json.dumps(findings))
        assert r.returncode == 0
        assert r.stdout == r_bare.stdout

    def test_cli_malformed_json_is_a_clean_error_not_a_traceback(self):
        """Regression (backstop review, #2170): malformed JSON must produce
        a clean, non-zero-exit error message on stderr — not an uncaught
        traceback, and never a silent `CLEAN_PASS_SUMMARY` on stdout."""
        r = _run(input_text="{not valid json")
        assert r.returncode != 0
        assert "Traceback" not in r.stderr
        assert "cannot interpret --findings input" in r.stderr
        assert rtf.CLEAN_PASS_SUMMARY not in r.stdout

    def test_cli_aggregated_json_object_with_top_findings_key_is_recognized(self):
        """Regression (backstop review, #2170): the actual aggregated
        `--json` object (`output-format.md`) keys its consolidated list as
        `topFindings`, not `findings` — the previous `_load_findings` fell
        through to an empty list for this exact real-world shape and
        rendered a false `CLEAN_PASS_SUMMARY`."""
        findings = [_finding()]
        r = _run(input_text=json.dumps({"overall": "warn", "topFindings": findings}))
        r_bare = _run(input_text=json.dumps(findings))
        assert r.returncode == 0
        assert r.stdout == r_bare.stdout

    def test_cli_per_agent_result_shape_with_issues_key_is_recognized(self):
        """Regression (backstop review, #2170): a raw per-agent
        `{status, issues, summary}` result
        (`knowledge/review-agent-output-contract.md`) keys its list as
        `issues`, not `findings` — same silent-empty failure mode as the
        `topFindings` case above."""
        findings = [_finding()]
        r = _run(
            input_text=json.dumps(
                {"status": "warn", "issues": findings, "summary": "x"}
            )
        )
        r_bare = _run(input_text=json.dumps(findings))
        assert r.returncode == 0
        assert r.stdout == r_bare.stdout

    def test_cli_unrecognized_dict_shape_is_a_clean_error_not_a_silent_clean_pass(self):
        """Regression (backstop review, #2170): a dict with none of
        `findings`/`topFindings`/`issues` as a list-valued key (e.g. a raw
        `{"agents": [...]}` object with no consolidated list at the top
        level) must error loudly rather than silently rendering
        `CLEAN_PASS_SUMMARY`."""
        r = _run(
            input_text=json.dumps(
                {"agents": [{"agentName": "x", "issues": [_finding()]}]}
            )
        )
        assert r.returncode != 0
        assert "cannot interpret --findings input" in r.stderr
        assert rtf.CLEAN_PASS_SUMMARY not in r.stdout


class TestReportSizes:
    """Every successful render records the round's untiered and tiered report sizes."""

    def test_untiered_report_inlines_full_message_and_suggested_fix(self):
        findings = [_finding(message="First sentence. Second sentence.")]
        ids = rtf.compute_ids(findings)
        assert rtf.render_untiered_report(findings, ids).splitlines() == [
            (
                "src/auth/login.ts:42 [structure-review] warning/medium — "
                "First sentence. Second sentence. (structure-review:src/auth/login.ts:42:warning)"
            ),
            "Suggested fix: Split into LoginController, RegistrationController, and PasswordResetController",
        ]

    def test_untiered_report_omits_the_fix_line_when_absent(self):
        findings = [_finding(suggestedFix="")]
        ids = rtf.compute_ids(findings)
        assert len(rtf.render_untiered_report(findings, ids).splitlines()) == 1

    def test_untiered_report_collapses_whitespace_runs_in_the_message(self):
        findings = [_finding(message="  One\n\n  two\tthree  ", suggestedFix="")]
        ids = rtf.compute_ids(findings)
        assert " — One two three (" in rtf.render_untiered_report(findings, ids)

    def test_untiered_report_renders_a_missing_message_as_empty_text(self):
        finding = _finding(suggestedFix="")
        del finding["message"]
        ids = rtf.compute_ids([finding])
        assert rtf.render_untiered_report([finding], ids) == (
            "src/auth/login.ts:42 [structure-review] warning/medium —  "
            "(structure-review:src/auth/login.ts:42:warning)"
        )

    def test_sizes_are_utf8_bytes_of_each_rendering(self):
        findings = [
            _finding(),
            _finding(line=7, message="Long — detail. More detail follows here."),
        ]
        ids = rtf.compute_ids(findings)
        sizes = rtf.measure_report_sizes(findings, ids)
        assert sizes == {
            "findings": 2,
            "untiered_bytes": len(rtf.render_untiered_report(findings, ids).encode("utf-8")),
            "tiered_bytes": len(rtf.render_tier1_report(findings, ids).encode("utf-8")),
        }
        assert sizes["tiered_bytes"] < sizes["untiered_bytes"]

    def test_sizes_match_a_hand_counted_byte_oracle(self):
        # Tier-1 line "f:1 [a] s/c — M. (a:f:1:s)" is 28 bytes (the dash is 3);
        # the untiered line adds " N." (31), then "\nSuggested fix: X" (17).
        # The Tier-1 report adds "\n" plus the 79-byte expansion hint.
        finding = {"agent": "a", "file": "f", "line": 1, "severity": "s",
                   "confidence": "c", "message": "M. N.", "suggestedFix": "X"}
        ids = rtf.compute_ids([finding])
        assert rtf.measure_report_sizes([finding], ids) == {
            "findings": 1,
            "untiered_bytes": 48,
            "tiered_bytes": 108,
        }

    def test_a_one_sentence_finding_with_no_fix_measures_larger_tiered(self):
        """The expansion hint makes the Tier-1 report the larger one here; the
        row records that as-is rather than clamping it."""
        findings = [_finding(message="Only sentence.", suggestedFix="")]
        sizes = rtf.measure_report_sizes(findings, rtf.compute_ids(findings))
        assert sizes["tiered_bytes"] > sizes["untiered_bytes"]

    def test_default_render_appends_one_row_with_the_session_id(self, tmp_path):
        findings = [_finding()]
        r = _run(input_text=json.dumps(findings), cwd=tmp_path, session="sess-1")
        assert r.returncode == 0
        (row,) = _size_rows(tmp_path)
        assert row["session_id"] == "sess-1"
        ids = rtf.compute_ids(findings)
        assert {
            k: row[k] for k in ("findings", "untiered_bytes", "tiered_bytes")
        } == rtf.measure_report_sizes(findings, ids)

    def test_zero_finding_render_records_the_clean_pass_summary_size(self, tmp_path):
        r = _run(input_text=json.dumps([]), cwd=tmp_path, session="s")
        assert r.returncode == 0
        (row,) = _size_rows(tmp_path)
        size = len(rtf.CLEAN_PASS_SUMMARY.encode("utf-8"))
        assert (row["findings"], row["untiered_bytes"], row["tiered_bytes"]) == (0, size, size)

    def test_session_flag_overrides_the_environment(self, tmp_path):
        _run(
            "--session",
            "from-flag",
            input_text=json.dumps([_finding()]),
            cwd=tmp_path,
            session="from-env",
        )
        (row,) = _size_rows(tmp_path)
        assert row["session_id"] == "from-flag"

    def test_claude_session_id_alone_supplies_the_session(self, tmp_path):
        _run(
            input_text=json.dumps([_finding()]),
            cwd=tmp_path,
            env_overrides={"CLAUDE_SESSION_ID": "legacy"},
        )
        (row,) = _size_rows(tmp_path)
        assert row["session_id"] == "legacy"

    def test_claude_code_session_id_wins_when_both_are_set(self, tmp_path):
        _run(
            input_text=json.dumps([_finding()]),
            cwd=tmp_path,
            env_overrides={"CLAUDE_CODE_SESSION_ID": "current", "CLAUDE_SESSION_ID": "legacy"},
        )
        (row,) = _size_rows(tmp_path)
        assert row["session_id"] == "current"

    def test_empty_claude_code_session_id_falls_through(self, tmp_path):
        _run(
            input_text=json.dumps([_finding()]),
            cwd=tmp_path,
            env_overrides={"CLAUDE_CODE_SESSION_ID": "", "CLAUDE_SESSION_ID": "legacy"},
        )
        (row,) = _size_rows(tmp_path)
        assert row["session_id"] == "legacy"

    def test_row_without_a_session_id_has_no_session_key(self, tmp_path):
        _run(input_text=json.dumps([_finding()]), cwd=tmp_path)
        (row,) = _size_rows(tmp_path)
        assert "session_id" not in row
        assert row["findings"] == 1

    def test_expand_all_render_records_the_round(self, tmp_path):
        findings = [_finding()]
        r = _run("--expand", "all", input_text=json.dumps(findings), cwd=tmp_path, session="s")
        ids = rtf.compute_ids(findings)
        assert r.returncode == 0
        assert r.stdout == (
            rtf.render_tier1_report(findings, ids) + "\n\n" + rtf.render_tier2_report(findings, ids) + "\n"
        )
        (row,) = _size_rows(tmp_path)
        assert {
            k: row[k] for k in ("findings", "untiered_bytes", "tiered_bytes")
        } == rtf.measure_report_sizes(findings, ids)

    def test_expand_one_render_records_the_same_sizes_as_the_default(self, tmp_path):
        findings = [_finding(), _finding(line=7)]
        ids = rtf.compute_ids(findings)
        default = _run(input_text=json.dumps(findings), cwd=tmp_path, session="s")
        expanded = _run("--expand", ids[1], input_text=json.dumps(findings), cwd=tmp_path, session="s")
        assert default.returncode == 0
        assert expanded.returncode == 0
        assert expanded.stdout == (
            rtf.render_tier1_report(findings, ids) + "\n\n" + rtf.render_tier2_block(findings[1], ids[1]) + "\n"
        )
        first, second = ({k: v for k, v in row.items() if k != "ts"} for row in _size_rows(tmp_path))
        assert first == second

    def test_unknown_expand_id_exits_1_and_records_nothing(self, tmp_path):
        r = _run("--expand", "no-such-id", input_text=json.dumps([_finding()]), cwd=tmp_path, session="s")
        assert r.returncode == 1
        assert _size_rows(tmp_path) == []

    def test_recording_leaves_stdout_as_the_tier1_report(self, tmp_path):
        findings = [_finding()]
        r = _run(input_text=json.dumps(findings), cwd=tmp_path, session="s")
        assert (
            r.stdout
            == rtf.render_tier1_report(findings, rtf.compute_ids(findings)) + "\n"
        )
        assert r.stderr == ""

    def test_a_size_measurement_that_raises_leaves_stdout_and_exit_code_unchanged(self, tmp_path):
        """A lone surrogate in the suggested fix cannot encode as UTF-8, so measuring
        the untiered report raises; the Tier-1 report never prints the fix."""
        findings = [_finding(suggestedFix="\udc80")]
        r = _run(input_text=json.dumps(findings), cwd=tmp_path, session="s")
        assert r.returncode == 0
        assert r.stdout == rtf.render_tier1_report(findings, rtf.compute_ids(findings)) + "\n"
        assert r.stderr == ""
        assert _size_rows(tmp_path) == []
