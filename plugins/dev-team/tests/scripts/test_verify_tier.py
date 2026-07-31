"""Unit tests for scripts/verify_tier.py (#1628).

Verification-mode tier resolution: declared per agent in the body, never
inferred, defaulting to the agent's own discovery tier when absent — and
failing toward the MORE expensive tier on a typo, never the cheaper one.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SCRIPTS_DIR = _PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import verify_tier

_AGENT = """---
name: {name}
description: d
model: {model}
effort: {effort}
---

# Agent

Scope: always
{extra}
Context needs: full-file
"""


def _agent(model="sonnet", effort="high", extra="", name="x-review"):
    return _AGENT.format(name=name, model=model, effort=effort, extra=extra)


class TestDefaults:
    def test_no_declaration_falls_back_to_the_discovery_tier(self):
        result = verify_tier.resolve(_agent(model="opus", effort="high"))
        assert result["model"] == "opus"
        assert result["effort"] == "high"
        assert result["opted_in"] is False
        assert result["errors"] == []

    def test_missing_frontmatter_model_effort_resolves_to_inherit(self):
        text = "---\nname: x-review\ndescription: d\n---\n\nScope: always\n"
        result = verify_tier.resolve(text)
        assert result["model"] == "inherit"
        assert result["effort"] == "inherit"


class TestOptIn:
    def test_both_declarations_are_honored(self):
        result = verify_tier.resolve(
            _agent(model="sonnet", effort="high", extra="Verify-model: haiku\nVerify-effort: medium")
        )
        assert result["model"] == "haiku"
        assert result["effort"] == "medium"
        assert result["opted_in"] is True

    def test_model_only_opt_in_keeps_the_discovery_effort(self):
        result = verify_tier.resolve(
            _agent(model="opus", effort="high", extra="Verify-model: haiku")
        )
        assert result["model"] == "haiku"
        assert result["effort"] == "high"
        assert result["opted_in"] is True

    def test_effort_only_opt_in_keeps_the_discovery_model(self):
        result = verify_tier.resolve(
            _agent(model="haiku", effort="high", extra="Verify-effort: low")
        )
        assert result["model"] == "haiku"
        assert result["effort"] == "low"

    def test_declaration_matching_is_case_insensitive(self):
        result = verify_tier.resolve(_agent(extra="verify-model: HAIKU"))
        assert result["model"] == "haiku"


class TestInvalidValues:
    def test_an_invalid_model_falls_back_to_discovery_and_reports_an_error(self):
        """Failing toward the MORE expensive tier is the right direction: a
        typo must never silently make a review cheaper than intended."""
        result = verify_tier.resolve(
            _agent(model="opus", effort="high", extra="Verify-model: cheep")
        )
        assert result["model"] == "opus"
        assert result["errors"]
        assert "Verify-model" in result["errors"][0]

    def test_an_invalid_effort_falls_back_to_discovery_and_reports_an_error(self):
        result = verify_tier.resolve(
            _agent(model="opus", effort="high", extra="Verify-effort: potato")
        )
        assert result["effort"] == "high"
        assert any("Verify-effort" in e for e in result["errors"])

    def test_an_invalid_declaration_does_not_count_as_opting_in(self):
        result = verify_tier.resolve(_agent(extra="Verify-model: cheep"))
        assert result["opted_in"] is False

    def test_a_frontmatter_declaration_is_ignored(self):
        """These are BODY declarations (#1333). A frontmatter `verify-model:`
        must not take effect — Claude Code would silently ignore it too."""
        text = (
            "---\nname: x-review\ndescription: d\nmodel: opus\neffort: high\n"
            "Verify-model: haiku\n---\n\nScope: always\n"
        )
        result = verify_tier.resolve(text)
        assert result["model"] == "opus"
        assert result["opted_in"] is False


class TestRealCorpus:
    @pytest.mark.parametrize(
        "agent", ["structure-review", "naming-review", "doc-review"]
    )
    def test_the_three_named_opt_ins_verify_at_haiku(self, agent):
        result = verify_tier.resolve_agent(agent)
        assert result["opted_in"] is True
        assert result["model"] == "haiku"
        assert result["errors"] == []

    @pytest.mark.parametrize("agent", ["correctness-review", "security-review"])
    def test_the_two_expensive_lenses_deliberately_do_not_opt_in(self, agent):
        """They wait for #1624's per-agent verification-yield data. Tiering
        them down on intuition is the mistake the contract exists to avoid."""
        result = verify_tier.resolve_agent(agent)
        assert result["opted_in"] is False

    def test_no_other_agent_opted_in_in_this_slice(self):
        opted = {
            path.stem
            for path in sorted((_PLUGIN_ROOT / "agents").glob("*-review.md"))
            if verify_tier.resolve_agent(path.stem)["opted_in"]
        }
        assert opted == {"structure-review", "naming-review", "doc-review"}

    def test_the_whole_corpus_declares_no_invalid_values(self):
        bad = {
            path.stem: verify_tier.resolve_agent(path.stem)["errors"]
            for path in sorted((_PLUGIN_ROOT / "agents").glob("*.md"))
            if verify_tier.resolve_agent(path.stem)["errors"]
        }
        assert bad == {}


class TestCli:
    def test_single_agent_lookup(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "verify_tier.py"), "--agent", "structure-review"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["agent"] == "structure-review"
        assert payload["model"] == "haiku"

    def test_all_exits_zero_on_a_clean_corpus(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "verify_tier.py"), "--all"],
            capture_output=True,
            text=True,
            check=True,
        )
        agents = json.loads(result.stdout)["agents"]
        assert len(agents) > 5
        assert all(a["errors"] == [] for a in agents)

    def test_unknown_agent_reports_an_error_and_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "verify_tier.py"), "--agent", "nope-review"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert json.loads(result.stdout)["errors"]


class TestContractDoc:
    def test_the_contract_is_stated_once_and_referenced_from_both_callers(self):
        contract = _PLUGIN_ROOT / "knowledge" / "verification-mode.md"
        assert contract.is_file()
        text = contract.read_text(encoding="utf-8")
        assert "insufficient-context" in text

        for skill in ("code-review", "build"):
            body = (_PLUGIN_ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            assert "verification-mode.md" in body, f"{skill} must reference the shared contract"

    def test_the_insufficient_context_escape_is_documented_as_mandatory(self):
        text = (_PLUGIN_ROOT / "knowledge" / "verification-mode.md").read_text(encoding="utf-8")
        assert "mandatory" in text.lower()
        assert "full-context re-dispatch" in text
