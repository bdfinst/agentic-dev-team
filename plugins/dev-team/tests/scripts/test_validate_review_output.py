"""Unit tests for skills/code-review/scripts/validate_review_output.py (#1998).

Session-report analysis found 18.2% of review-agent outputs failing the
shared JSON contract and being silently discarded — no agent name, no raw
output, no reason recorded anywhere. This module is the deterministic
detector + diagnostic logger that closes that gap. What these tests protect:
every documented failure shape is classified correctly (including the two
dimensions — `shape` and `extraction` — surviving independently rather than
one overwriting the other), the raw-output prefix is secret-redacted before
persistence, the logged `agent` name matches the ledger's closed vocabulary,
the JSONL append is symlink-safe, and — per this repo's "make it fail on
purpose once before you trust it" rule — the logger is proven to actually
write a diagnostic on a deliberately-malformed input rather than merely
being trusted to.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import validate_review_output as vac

_SCRIPT_PATH = _SCRIPTS_DIR / "validate_review_output.py"

_VALID_PAYLOAD = json.dumps(
    {"status": "warn", "issues": [{"severity": "warning", "message": "x"}], "summary": "1 warning"}
)


class TestCleanValid:
    def test_well_formed_json_is_valid(self):
        result = vac.classify_and_validate(_VALID_PAYLOAD)
        assert result == {"valid": True, "shape": vac.SHAPE_CLEAN, "extraction": vac.SHAPE_CLEAN, "error": None}

    def test_pass_status_with_empty_issues_is_valid(self):
        payload = json.dumps({"status": "pass", "issues": [], "summary": "clean"})
        result = vac.classify_and_validate(payload)
        assert result["valid"] is True

    def test_surrounding_whitespace_is_tolerated(self):
        result = vac.classify_and_validate(f"\n\n  {_VALID_PAYLOAD}  \n")
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_CLEAN


class TestEmpty:
    def test_empty_string_is_classified_empty(self):
        result = vac.classify_and_validate("")
        assert result == {
            "valid": False,
            "shape": vac.SHAPE_EMPTY,
            "extraction": None,
            "error": "output was empty or whitespace-only",
        }

    def test_whitespace_only_is_classified_empty(self):
        result = vac.classify_and_validate("   \n\t  ")
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_EMPTY


class TestFenced:
    def test_json_fenced_in_a_code_block_is_recovered(self):
        raw = f"```json\n{_VALID_PAYLOAD}\n```"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_FENCED
        assert result["extraction"] == vac.SHAPE_FENCED

    def test_fenced_block_without_language_tag_is_recovered(self):
        raw = f"```\n{_VALID_PAYLOAD}\n```"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_FENCED


class TestProsePreamble:
    def test_prose_before_the_json_object_is_recovered(self):
        raw = f"Here is my review:\n\n{_VALID_PAYLOAD}"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_PROSE_PREAMBLE
        assert result["extraction"] == vac.SHAPE_PROSE_PREAMBLE

    def test_prose_after_the_json_object_is_recovered(self):
        raw = f"{_VALID_PAYLOAD}\n\nLet me know if you have questions."
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_PROSE_PREAMBLE

    def test_a_literal_brace_inside_a_json_string_value_does_not_corrupt_depth_counting(self):
        """`_find_first_json_object`'s in-string brace-balancing state machine
        must not mistake a `{`/`}` inside a quoted string value for a
        structural brace. Uses an UNBALANCED embedded brace (a single `}`
        with no partner) — a naive, non-string-aware brace counter would hit
        depth zero prematurely inside the string and mis-slice the candidate,
        whereas the string-aware scanner still recovers the full object. A
        balanced embedded pair (the original form of this test) passes even
        without in-string tracking, so it provides no regression coverage."""
        payload = json.dumps(
            {
                "status": "warn",
                "issues": [{"severity": "warning", "message": "found a stray } without partner"}],
                "summary": "x",
            }
        )
        raw = f"Here is my review:\n\n{payload}\n\ndone."
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_PROSE_PREAMBLE

    def test_a_backslash_escaped_quote_inside_a_string_value_does_not_desync_scanning(self):
        """The `escape` half of the in-string state machine (a `\\"` must not
        be treated as the string's closing quote) had zero coverage — a
        message value containing an escaped quote adjacent to a brace is the
        input that would expose a bug there."""
        payload = json.dumps(
            {
                "status": "warn",
                "issues": [{"severity": "warning", "message": 'found "quoted" text with { a brace }'}],
                "summary": "x",
            }
        )
        raw = f"Here is my review:\n\n{payload}\n\ndone."
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_PROSE_PREAMBLE

    def test_an_unbalanced_brace_in_the_preamble_does_not_prevent_recovering_a_later_valid_object(self):
        """Regression test (#1998 second review round, correctness-review
        ERROR): `_find_first_json_object` used to scan only from the FIRST
        `{` in the text and never retry a later one. A preamble sentence
        quoting code — a realistic thing for a review lens to do — can itself
        contain an unbalanced `{`, which made a fully contract-valid report
        misclassify as `truncated`, excluding the agent from
        `dispatch_reconcile.py`'s `--returned` set and forcing a spurious
        retry."""
        payload = json.dumps({"status": "pass", "issues": [], "summary": "ok"})
        raw = f"The handler `if (x) {{` is fine.\n{payload}"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_PROSE_PREAMBLE

    def test_a_stray_quote_and_brace_together_in_the_preamble_still_recovers_the_real_object(self):
        """A second manifestation of the same root cause: a stray `"` in the
        preamble can also desync in-string tracking for the rest of the scan.
        The retry-at-next-`{` loop recovers the real object regardless,
        because each retry starts a fresh scan (fresh `in_string` state) from
        its own candidate `{`."""
        payload = json.dumps({"status": "pass", "issues": [], "summary": "ok"})
        raw = f'He said "hi {{" -- {payload}'
        result = vac.classify_and_validate(raw)
        assert result["valid"] is True
        assert result["shape"] == vac.SHAPE_PROSE_PREAMBLE


class TestTruncated:
    def test_unbalanced_braces_is_truncated(self):
        raw = '{"status": "warn", "issues": [{"severity": "error", "message": "cut off'
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_TRUNCATED
        assert result["extraction"] is None

    def test_error_message_is_captured_for_truncation(self):
        raw = '{"status": "warn", "issues": ['
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_TRUNCATED
        assert result["error"] == "unbalanced braces — output likely truncated at a token limit"

    def test_equal_raw_brace_counts_can_still_be_truncated(self):
        """A naive `text.count('{') > text.count('}')` heuristic would miss
        this: the string value itself contains a stray `}` that balances the
        raw count even though the object never actually closes."""
        raw = '{"status": "warn", "issues": ["}'
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_TRUNCATED


class TestMalformedJson:
    """A balanced ``{...}`` candidate that still fails `json.loads` is
    distinct from truncation — the output finished, it just wasn't valid
    JSON (unquoted keys, a trailing comma, a Python-repr dict). Reusing
    `truncated` for this (the original defect) sends any follow-on
    fix-by-shape work at the wrong remedy — a retry-with-more-tokens fix for
    what is actually a malformed-syntax problem."""

    def test_unquoted_keys_is_malformed_json_not_truncated(self):
        raw = "prose {retry: true} more prose"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_MALFORMED_JSON

    def test_trailing_comma_is_malformed_json(self):
        raw = '{"status": "warn", "issues": [],}'
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_MALFORMED_JSON

    def test_python_repr_dict_is_malformed_json(self):
        raw = "{'status': 'warn', 'issues': []}"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_MALFORMED_JSON

    def test_malformed_json_inside_a_fence_is_labeled_fenced_not_prose_preamble(self):
        """Regression test (#1998 second review round, correctness-review
        WARNING): a malformed object inside a ```json fence used to fall
        through to the positional brace-scanner on the full (still
        fence-wrapped) text, which always relabeled it `prose-preamble` since
        the fence markers made the candidate substring differ from the
        stripped text. A fence match requires a closing delimiter, so its
        contents are a complete span — there is no further fallback once a
        fence is found, and the extraction label must say so."""
        raw = "```json\n{status: pass}\n```"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_MALFORMED_JSON
        assert result["extraction"] == vac.SHAPE_FENCED


class TestSchemaDrift:
    def test_invalid_status_enum_is_schema_drift(self):
        payload = json.dumps({"status": "ok", "issues": [], "summary": "x"})
        result = vac.classify_and_validate(payload)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT
        assert result["extraction"] == vac.SHAPE_CLEAN
        assert result["error"] == f"status='ok' not one of {sorted(vac._VALID_STATUSES)}"

    def test_missing_issues_field_is_schema_drift(self):
        payload = json.dumps({"status": "pass", "summary": "x"})
        result = vac.classify_and_validate(payload)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT

    def test_issues_not_a_list_is_schema_drift(self):
        payload = json.dumps({"status": "pass", "issues": "none", "summary": "x"})
        result = vac.classify_and_validate(payload)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT

    def test_invalid_severity_enum_is_schema_drift(self):
        payload = json.dumps(
            {"status": "warn", "issues": [{"severity": "critical", "message": "x"}], "summary": "x"}
        )
        result = vac.classify_and_validate(payload)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT

    def test_missing_summary_field_is_schema_drift(self):
        payload = json.dumps({"status": "pass", "issues": []})
        result = vac.classify_and_validate(payload)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT

    def test_top_level_array_instead_of_object_is_schema_drift(self):
        result = vac.classify_and_validate("[1, 2, 3]")
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT

    def test_schema_drift_survives_fenced_extraction(self):
        """A schema-invalid payload wrapped in a fence must still report
        which extraction path recovered it, not just that it drifted."""
        payload = json.dumps({"status": "ok", "issues": [], "summary": "x"})
        raw = f"```json\n{payload}\n```"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT
        assert result["extraction"] == vac.SHAPE_FENCED

    def test_schema_drift_survives_prose_preamble_extraction(self):
        payload = json.dumps({"status": "ok", "issues": [], "summary": "x"})
        raw = f"Here is my review:\n\n{payload}"
        result = vac.classify_and_validate(raw)
        assert result["valid"] is False
        assert result["shape"] == vac.SHAPE_SCHEMA_DRIFT
        assert result["extraction"] == vac.SHAPE_PROSE_PREAMBLE


class TestNotJson:
    def test_plain_prose_with_no_braces_is_not_json(self):
        result = vac.classify_and_validate("I reviewed the diff and found no issues.")
        assert result == {
            "valid": False,
            "shape": vac.SHAPE_NOT_JSON,
            "extraction": None,
            "error": "no JSON object found in output",
        }


class TestFailureShapeInvariants:
    def test_failure_shapes_and_success_shapes_are_disjoint(self):
        assert vac.FAILURE_SHAPES.isdisjoint(vac.SUCCESS_SHAPES)

    def test_every_classify_result_shape_is_one_of_the_two_closed_sets(self):
        for raw in (
            "",
            _VALID_PAYLOAD,
            f"```json\n{_VALID_PAYLOAD}\n```",
            f"prose\n{_VALID_PAYLOAD}",
            "not json at all",
            '{"status": "warn", "issues": [',
            "{'status': 'warn'}",
            json.dumps({"status": "ok", "issues": [], "summary": "x"}),
        ):
            result = vac.classify_and_validate(raw)
            assert result["shape"] in vac.FAILURE_SHAPES or result["shape"] in vac.SUCCESS_SHAPES


class TestRedaction:
    def test_hardcoded_key_assignment_is_redacted(self):
        raw = 'not json, but found api_key: "sk-abcdefghijklmnopqrstuvwx" in config.py'
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert "sk-abcdefghijklmnopqrstuvwx" not in entry["raw_prefix"]
        assert "[REDACTED]" in entry["raw_prefix"]

    def test_aws_style_key_is_redacted(self):
        # Built via concatenation, not a single literal, so a secret-scanner
        # (gitleaks) does not itself flag this synthetic fixture as a real key.
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        raw = f"found {fake_key} hardcoded in src/config.ts"
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert fake_key not in entry["raw_prefix"]

    def test_github_token_is_redacted(self):
        raw = "ghp_" + "a" * 36 + " was hardcoded"
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert ("ghp_" + "a" * 36) not in entry["raw_prefix"]

    def test_segmented_vendor_key_is_redacted(self):
        """The `sk-` pattern must match hyphen-segmented token bodies
        (`sk-ant-...`, `sk-proj-...`), not just an unbroken alphanumeric run —
        the unsegmented form the original pattern only covered would leave
        an Anthropic- or OpenAI-project-style key unredacted."""
        fake_key = "sk-ant-api03-" + "A" * 40
        raw = f"found {fake_key} hardcoded in config.py"
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert fake_key not in entry["raw_prefix"]

    def test_slack_token_is_redacted(self):
        fake_token = "xoxb-" + "1" * 10
        raw = f"found {fake_token} hardcoded"
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert fake_token not in entry["raw_prefix"]

    def test_jwt_shaped_token_is_redacted(self):
        fake_jwt = "eyJ" + "a" * 10 + "." + "b" * 10 + "." + "c" * 10
        raw = f"found {fake_jwt} hardcoded"
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert fake_jwt not in entry["raw_prefix"]

    def test_complete_pem_block_is_redacted(self):
        # Concatenated, not a single literal — see test_aws_style_key_is_redacted:
        # gitleaks' private-key rule matches a contiguous BEGIN/END block.
        begin_marker = "-----BEGIN " + "PRIVATE KEY-----"
        end_marker = "-----END " + "PRIVATE KEY-----"
        fake_pem = f"{begin_marker}\n" + "A" * 40 + f"\n{end_marker}"
        raw = f"found:\n{fake_pem}\nin config"
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert "A" * 40 not in entry["raw_prefix"]
        assert "PRIVATE KEY" not in entry["raw_prefix"]

    def test_truncated_pem_block_with_no_end_marker_is_still_redacted(self):
        """The failure shape this module logs most (`truncated`) cuts output
        mid-content — a PEM block with no closing END marker must still be
        redacted from BEGIN to end-of-string, not left in cleartext because
        the balanced pattern requires an END it will never see."""
        begin_marker = "-----BEGIN " + "PRIVATE KEY-----"
        fake_pem_body = "A" * 40
        raw = f"{begin_marker}\n" + fake_pem_body
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert fake_pem_body not in entry["raw_prefix"]

    def test_truncated_hardcoded_key_with_no_closing_quote_is_still_redacted(self):
        """The canonical hardcoded-key pattern used to require a closing
        quote, which defeats redaction on exactly the `truncated` shape this
        module exists to classify — output cut mid-string, before the
        closing quote ever arrives."""
        raw = 'not json, but found password: "S3cr3tP@ssw0rd'
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert "S3cr3tP@ssw0rd" not in entry["raw_prefix"]

    def test_redaction_runs_before_truncation_so_a_boundary_straddling_secret_is_still_caught(self):
        """A secret that would otherwise start right at the
        `_RAW_PREFIX_LEN` cut must still be redacted — redaction has to run
        on the full text first, not on the already-truncated slice."""
        padding = "x" * (vac._RAW_PREFIX_LEN - 10)
        # Concatenated, not a single literal — see test_aws_style_key_is_redacted.
        secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        raw = padding + " " + secret + " end"
        entry = vac.build_failure_entry("security-review", raw, vac.classify_and_validate(raw))
        assert secret not in entry["raw_prefix"]

    def test_text_with_no_secret_shape_is_unchanged(self):
        raw = "Sure, here's my analysis: " + "x" * 100
        entry = vac.build_failure_entry("doc-review", raw, vac.classify_and_validate(raw))
        assert entry["raw_prefix"] == raw[: vac._RAW_PREFIX_LEN]


class TestErrorFieldRedactionAndCap:
    """`_validate_schema` interpolates agent-controlled values (`status`,
    `severity`) into the `error` string with `!r` — unlike `raw_prefix`, this
    field was neither redacted nor capped before #1998's second review round
    (security-review WARNING), so a drifting agent could write an
    arbitrarily long, secret-bearing `error` straight into
    `contract-failures.jsonl` and every `dispatchFailures[].error` consumer
    downstream of `main()`'s printed output."""

    def test_secret_shaped_status_value_is_redacted_out_of_the_logged_error(self):
        secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        payload = json.dumps({"status": f"leaked {secret}", "issues": [], "summary": "x"})
        diagnostic = vac.classify_and_validate(payload)
        entry = vac.build_failure_entry("doc-review", payload, diagnostic)
        assert secret not in entry["error"]

    def test_long_error_is_capped_in_the_logged_entry(self):
        diagnostic = {
            "valid": False,
            "shape": vac.SHAPE_SCHEMA_DRIFT,
            "extraction": vac.SHAPE_CLEAN,
            "error": "x" * (vac._ERROR_MAX_LEN + 50),
        }
        entry = vac.build_failure_entry("doc-review", "raw", diagnostic)
        assert len(entry["error"]) == vac._ERROR_MAX_LEN

    def test_cli_printed_error_is_also_redacted_and_capped(self, tmp_path):
        secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        payload = json.dumps({"status": f"leaked {secret}", "issues": [], "summary": "x"})
        input_file = tmp_path / "raw.txt"
        input_file.write_text(payload, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--agent",
                "doc-review",
                "--file",
                str(input_file),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        printed = json.loads(result.stdout)
        assert secret not in printed["error"]


class TestAgentNameNormalization:
    def test_plugin_qualified_agent_name_is_stripped(self):
        """The logged `agent` field must match `boundary-events.jsonl`'s
        `matched_rule` vocabulary (bare agent names) — a qualified
        `dev-team:<name>` dispatch form would otherwise silently produce a
        phantom agent with 0 dispatches in `contract_failure_report.py`'s
        join, the same class of bug #1461 found in the ledger hook itself."""
        entry = vac.build_failure_entry(
            "dev-team:concurrency-review", "not json", vac.classify_and_validate("not json")
        )
        assert entry["agent"] == "concurrency-review"

    def test_bare_agent_name_is_unchanged(self):
        entry = vac.build_failure_entry("concurrency-review", "not json", vac.classify_and_validate("not json"))
        assert entry["agent"] == "concurrency-review"

    def test_other_plugin_prefix_is_left_untouched(self):
        entry = vac.build_failure_entry(
            "other-plugin:some-review", "not json", vac.classify_and_validate("not json")
        )
        assert entry["agent"] == "other-plugin:some-review"


class TestBuildFailureEntryInvariant:
    def test_raises_on_a_valid_diagnostic(self):
        with pytest.raises(ValueError):
            vac.build_failure_entry("doc-review", _VALID_PAYLOAD, vac.classify_and_validate(_VALID_PAYLOAD))

    def test_entry_carries_the_extraction_field(self):
        payload = json.dumps({"status": "ok", "issues": [], "summary": "x"})
        raw = f"```json\n{payload}\n```"
        entry = vac.build_failure_entry("doc-review", raw, vac.classify_and_validate(raw))
        assert entry["extraction"] == vac.SHAPE_FENCED
        assert entry["shape"] == vac.SHAPE_SCHEMA_DRIFT


class TestFailureLogging:
    def test_deliberate_failure_is_actually_logged(self, tmp_path):
        """The detector must PROVE it fires — per this repo's 'make it fail
        on purpose once before you trust it' rule — rather than being
        trusted on the strength of the classifier tests alone."""
        entry = vac.build_failure_entry("concurrency-review", "not json at all", vac.classify_and_validate("not json at all"))
        written = vac.log_failure(entry, cwd=tmp_path)

        assert written is not None
        assert written.exists()
        rows = [json.loads(line) for line in written.read_text(encoding="utf-8").splitlines()]
        assert rows == [entry]

    def test_logged_entry_carries_agent_shape_error_and_raw_prefix(self):
        raw = "Sure, here's my analysis: " + "x" * 500
        diagnostic = vac.classify_and_validate(raw)
        entry = vac.build_failure_entry("doc-review", raw, diagnostic, timestamp="2026-08-26T00:00:00Z")

        assert entry["agent"] == "doc-review"
        assert entry["shape"] == diagnostic["shape"]
        assert entry["error"] == vac._safe_error(diagnostic["error"])
        assert entry["raw_prefix"] == raw[: vac._RAW_PREFIX_LEN]
        assert entry["timestamp"] == "2026-08-26T00:00:00Z"

    def test_raw_prefix_is_capped_at_the_configured_length(self):
        raw = "not json " * 100
        entry = vac.build_failure_entry("doc-review", raw, vac.classify_and_validate(raw))
        assert len(entry["raw_prefix"]) == vac._RAW_PREFIX_LEN

    def test_multiple_failures_append_rather_than_overwrite(self, tmp_path):
        first = vac.build_failure_entry("a-review", "bad 1", vac.classify_and_validate("bad 1"))
        second = vac.build_failure_entry("b-review", "bad 2", vac.classify_and_validate("bad 2"))
        vac.log_failure(first, cwd=tmp_path)
        path = vac.log_failure(second, cwd=tmp_path)

        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert rows == [first, second]

    def test_write_failure_fails_open_and_returns_none(self, tmp_path):
        """`log_failure`'s documented fail-open contract — a write failure
        must never raise, only return `None` — was previously untested;
        only the success path was covered."""
        blocking_file = tmp_path / ".claude"
        blocking_file.write_text("not a directory", encoding="utf-8")
        entry = vac.build_failure_entry("doc-review", "bad", vac.classify_and_validate("bad"))

        result = vac.log_failure(entry, cwd=tmp_path)

        assert result is None

    def test_append_does_not_follow_a_symlinked_stream_path(self, tmp_path):
        """`log_failure` must delegate to `atomic_state.append_line_locked`
        (symlink-safe, O_NOFOLLOW) rather than a bare `open(..., "a")` — a
        pre-planted symlink at the stream path must never be followed to
        redirect a diagnostic (which may carry repo-derived text) to an
        arbitrary file (#1889's hardening, extended to this emitter).

        Also asserts the return value: `log_failure` passes
        `fail_open=False` through to `append_line_locked` specifically so
        the O_NOFOLLOW rejection this test plants raises inside the lock and
        is caught by `log_failure`'s OWN `except Exception` — rather than
        being silently swallowed by `append_line_locked`'s own default
        fail-open, which would make `log_failure` return the log path even
        though nothing was actually written, contradicting its documented
        'returns `None` when the write failed' contract."""
        if not hasattr(os, "O_NOFOLLOW"):
            pytest.skip("platform has no O_NOFOLLOW")
        metrics_dir = tmp_path / ".claude" / "metrics"
        metrics_dir.mkdir(parents=True)
        target = tmp_path / "outside-target.txt"
        log = metrics_dir / "contract-failures.jsonl"
        os.symlink(str(target), str(log))

        entry = vac.build_failure_entry("doc-review", "bad", vac.classify_and_validate("bad"))
        written = vac.log_failure(entry, cwd=tmp_path)

        assert written is None, "a rejected symlinked write must report failure, not the log path"
        assert not target.exists(), "symlinked stream path must not be followed"
        assert os.path.islink(log), "the planted symlink itself must be left untouched"


class TestCli:
    def test_valid_output_exits_zero_and_writes_nothing(self, tmp_path):
        input_file = tmp_path / "raw.txt"
        input_file.write_text(_VALID_PAYLOAD, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--agent",
                "correctness-review",
                "--file",
                str(input_file),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["valid"] is True
        assert not (tmp_path / ".claude" / "metrics" / "contract-failures.jsonl").exists()

    def test_invalid_output_exits_nonzero_and_logs_a_diagnostic(self, tmp_path):
        input_file = tmp_path / "raw.txt"
        input_file.write_text("I found nothing wrong with this code.", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--agent",
                "concurrency-review",
                "--file",
                str(input_file),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["agent"] == "concurrency-review"
        assert payload["valid"] is False
        assert payload["shape"] == vac.SHAPE_NOT_JSON

        log_path = tmp_path / ".claude" / "metrics" / "contract-failures.jsonl"
        assert log_path.exists()
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["agent"] == "concurrency-review"
        assert row["shape"] == vac.SHAPE_NOT_JSON

    def test_dry_run_never_writes_the_log(self, tmp_path):
        input_file = tmp_path / "raw.txt"
        input_file.write_text("not json", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--agent",
                "doc-review",
                "--file",
                str(input_file),
                "--cwd",
                str(tmp_path),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1
        assert not (tmp_path / ".claude" / "metrics" / "contract-failures.jsonl").exists()

    def test_reads_from_stdin_when_file_is_a_dash(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--agent",
                "structure-review",
                "--file",
                "-",
                "--cwd",
                str(tmp_path),
            ],
            input=_VALID_PAYLOAD,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout)["valid"] is True

    def test_plugin_qualified_agent_name_is_normalized_in_output_and_log(self, tmp_path):
        input_file = tmp_path / "raw.txt"
        input_file.write_text("not json", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--agent",
                "dev-team:concurrency-review",
                "--file",
                str(input_file),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        payload = json.loads(result.stdout)
        assert payload["agent"] == "concurrency-review"
        log_path = tmp_path / ".claude" / "metrics" / "contract-failures.jsonl"
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["agent"] == "concurrency-review"
