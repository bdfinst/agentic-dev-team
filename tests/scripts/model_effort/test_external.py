"""The wrappers that reach into scripts outside the package (model_effort.external)."""

from __future__ import annotations

import pytest
from model_effort import external


class TestExternalScriptWrappers:
    """These fail when an upstream script renames the private helper the wrapper reaches."""

    def test_session_identity_variable_is_scrubbed_and_home_is_kept(self):
        assert external.should_scrub_env_var("CLAUDE_CODE_SESSION_ID") is True
        assert external.should_scrub_env_var("HOME") is False

    @pytest.mark.parametrize(
        ("value", "valid"),
        [("haiku", True), ("claude-opus-4-8", True), ("gpt-4", False), ("", False)],
    )
    def test_model_is_valid_against_the_contract_enum(self, value, valid):
        assert external.model_is_valid(value, ["haiku", "sonnet", "opus"]) is valid


class TestContractEnums:
    def test_models_and_efforts_come_from_the_agent_contract(self):
        enums = external.contract_enums()

        assert enums is not None
        models, efforts = enums
        assert {"haiku", "sonnet"} <= set(models)
        assert {"low", "high"} <= set(efforts)

    def test_unreadable_contract_yields_none(self, monkeypatch):
        monkeypatch.setattr(
            external.agent_contract_validator(), "load_contract", lambda: None
        )

        assert external.contract_enums() is None
