"""The wrappers that reach into scripts outside the package (model_effort.external)."""

from __future__ import annotations

import json

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


class TestContractDrift:
    """A contract or helper that changed shape is the harness's fault, never a refused value."""

    def test_a_renamed_model_check_is_a_contract_error(self, monkeypatch):
        monkeypatch.delattr(external.agent_contract_validator(), "_model_is_valid")

        with pytest.raises(external.ExternalContractError, match="_model_is_valid"):
            external.model_is_valid("haiku", ["haiku"])

    def test_a_model_check_that_stops_returning_a_bool_is_a_contract_error(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            external.agent_contract_validator(), "_model_is_valid", lambda *_: "yes"
        )

        with pytest.raises(external.ExternalContractError, match="_model_is_valid"):
            external.model_is_valid("haiku", ["haiku"])

    @pytest.mark.parametrize(
        "contract",
        [
            [],
            {},
            {"fields": {}},
            {"fields": {"model": {"enum": ["haiku"]}}},
            {"fields": {"model": {"enum": "haiku"}, "effort": {"enum": ["low"]}}},
            {"fields": {"model": {"enum": ["haiku"]}, "effort": {"enum": [3]}}},
        ],
        ids=["list", "no-fields", "no-model", "no-effort", "enum-not-list", "enum-not-str"],
    )
    def test_a_contract_of_another_shape_is_a_contract_error(self, monkeypatch, contract):
        monkeypatch.setattr(
            external.agent_contract_validator(), "load_contract", lambda: contract
        )

        with pytest.raises(external.ExternalContractError, match="agent-contract"):
            external.contract_enums()


def _two_agent_expected_dir(tmp_path):
    entry = {
        "fixture": "stem",
        "applicableAgents": ["named", "other"],
        "agents": {
            "named": {"expectedStatus": "pass"},
            "other": {"expectedStatus": "fail"},
        },
    }
    (tmp_path / "stem.json").write_text(json.dumps(entry), encoding="utf-8")
    return tmp_path


class TestGradeAgainstExpected:
    def test_only_the_named_agents_entry_is_graded(self, tmp_path):
        rows = external.grade_against_expected(
            _two_agent_expected_dir(tmp_path),
            "stem",
            "named",
            {"status": "pass", "issues": [], "summary": ""},
        )

        assert rows == [("stem::named", True, [])]

    @pytest.mark.parametrize(
        "returned",
        [
            ([("pair", "yes", [])], None),
            ([("pair", 1, [])], None),
            ([["pair", True, []]], None),
            ((("pair", True, []),), None),
            ([("pair", True, ())], None),
            ([("pair", True, [], "extra")], None),
            ([("pair", True, [])], None, "extra"),
        ],
        ids=[
            "passed-not-bool",
            "passed-int",
            "row-not-tuple",
            "rows-not-list",
            "messages-not-list",
            "long-row",
            "long-return",
        ],
    )
    def test_a_changed_return_shape_is_a_contract_error(
        self, tmp_path, monkeypatch, returned
    ):
        monkeypatch.setattr(
            external.eval_grade(), "run_grading", lambda **_kwargs: returned
        )

        with pytest.raises(external.ExternalContractError, match="run_grading"):
            external.grade_against_expected(tmp_path, "stem", "named", {})

    def test_the_expected_shape_is_returned_unchanged(self, tmp_path, monkeypatch):
        rows = [("a::x", True, []), ("b::x", False, ["m"])]
        monkeypatch.setattr(
            external.eval_grade(), "run_grading", lambda **_kwargs: (rows, None)
        )

        assert external.grade_against_expected(tmp_path, "stem", "x", {}) == rows
