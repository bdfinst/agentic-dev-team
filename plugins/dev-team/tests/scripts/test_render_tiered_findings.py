"""Unit tests for skills/code-review/scripts/render_tiered_findings.py (#2170).

Covers finding-id derivation (including the ordinal-suffix collision case),
Tier-1 rendering, Tier-2 rendering via `--expand <id>|all`, the unknown-id
failure contract, and the zero-finding clean-pass path.
"""

from __future__ import annotations

import json
import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import render_tiered_findings as rtf

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


def _run(*args, input_text=None):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


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

    def test_cli_malformed_json_propagates_uncaught_error(self):
        """Pins current behavior (matches the sibling script
        finding_signature.py, no documented contract requires catching this):
        malformed JSON is not caught — json.loads's exception propagates,
        producing a non-zero exit and a traceback on stderr."""
        r = _run(input_text="{not valid json")
        assert r.returncode != 0
        assert "JSONDecodeError" in r.stderr
