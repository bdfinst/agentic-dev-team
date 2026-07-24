"""#85: the test-layer-gates eval corpus (tlg-*) is structurally well-formed —
1:1 fixture<->expected pairing, valid skill schema, valid gate/layer vocab.
Deterministic structural guard; behavioral gate-firing is graded by
/agent-eval --skill test-design-advisor (model-judged).

Ported from tests/repo/eval_tlg_fixtures.bats (issue #672).
"""

from __future__ import annotations

import json
from pathlib import Path

from _repo_root import REPO_ROOT

FIXTURES = REPO_ROOT / "evals" / "fixtures"
EXPECTED = REPO_ROOT / "evals" / "expected"

GATE_VOCAB = {"A", "B", "C", "D", "redundancy", "ambiguity"}
LAYER_VOCAB = {"unit", "integration", "component", "contract", "E2E"}


def _tlg_fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("tlg-*.md"))


def _tlg_expected() -> list[Path]:
    return sorted(EXPECTED.glob("tlg-*.json"))


def test_tlg_there_are_11_fixtures_one_per_80_gate_row() -> None:
    assert len(_tlg_fixtures()) == 11


def test_tlg_every_fixture_has_a_matching_expected_json() -> None:
    for fixture in _tlg_fixtures():
        stem = fixture.stem
        assert (EXPECTED / f"{stem}.json").is_file(), f"missing expected: {stem}.json"


def test_tlg_every_expected_json_has_a_matching_fixture() -> None:
    for expected in _tlg_expected():
        stem = expected.stem
        assert (FIXTURES / f"{stem}.md").is_file(), f"missing fixture: {stem}.md"


def test_tlg_every_expected_json_parses_and_declares_the_advisor_skill() -> None:
    for expected in _tlg_expected():
        data = json.loads(expected.read_text())
        assert "test-design-advisor" in data.get("applicableSkills", []), (
            f"not a test-design-advisor skill fixture: {expected}"
        )


def test_tlg_fixture_field_matches_the_file_stem() -> None:
    for expected in _tlg_expected():
        stem = expected.stem
        data = json.loads(expected.read_text())
        assert data["fixture"] == stem, (
            f"fixture field mismatch in {expected}: {data['fixture']} != {stem}"
        )


def test_tlg_skills_block_has_the_required_array_fields() -> None:
    for expected in _tlg_expected():
        data = json.loads(expected.read_text())
        skill = data["skills"]["test-design-advisor"]
        for field in (
            "expectedGates",
            "expectedLayers",
            "mustMention",
            "mustNotMention",
        ):
            assert isinstance(skill[field], list), f"bad skills block: {expected}"


def test_tlg_expectedgates_use_the_gate_vocabulary() -> None:
    for expected in _tlg_expected():
        data = json.loads(expected.read_text())
        gates = data["skills"]["test-design-advisor"]["expectedGates"]
        assert all(g in GATE_VOCAB for g in gates), f"invalid gate value in {expected}"


def test_tlg_expectedlayers_use_the_test_pyramid_vocabulary() -> None:
    for expected in _tlg_expected():
        data = json.loads(expected.read_text())
        layers = data["skills"]["test-design-advisor"]["expectedLayers"]
        assert all(layer in LAYER_VOCAB for layer in layers), (
            f"invalid layer value in {expected}"
        )


def test_tlg_all_four_behavior_gates_a_b_c_d_plus_redundancy_and_ambiguity_represented() -> (
    None
):
    seen: set[str] = set()
    for expected in _tlg_expected():
        data = json.loads(expected.read_text())
        seen.update(data["skills"]["test-design-advisor"]["expectedGates"])
    for gate in ("A", "B", "C", "D", "redundancy", "ambiguity"):
        assert gate in seen, f"gate not represented in corpus: {gate}"
