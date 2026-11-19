"""Content contract for the system-test-design knowledge files.

Each file must carry every item the spec lists for it, so the skill that cites
them never depends on material outside the repo.
"""

import re
from pathlib import Path

KNOWLEDGE = Path(__file__).resolve().parents[2] / "plugins/dev-team/knowledge"


def _read(name: str) -> str:
    return (KNOWLEDGE / name).read_text()


def _in_order(text: str, terms: list[str]) -> bool:
    pos = -1
    for term in terms:
        nxt = text.find(term, pos + 1)
        if nxt == -1:
            return False
        pos = nxt
    return True


def test_entangled_workflows_has_three_kinds_with_all_parts() -> None:
    text = _read("entangled-workflows.md")
    for kind in ("Shared table or schema", "Entangled value object", "Lockstep deployment"):
        match = re.search(rf"^## {kind}\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
        assert match, kind
        for part in ("**Signs:**", "**What the guarding E2E asserts:**", "**Decoupling step:**"):
            assert part in match.group(1), f"{kind} missing {part}"


def test_entangled_workflows_lists_value_object_examples_and_labels() -> None:
    text = _read("entangled-workflows.md")
    for term in ("Money", "Identifier", "Status", "Date/time", "Measured quantity", "observed", "inferred"):
        assert term in text, term


def test_ownership_decision_has_six_questions_in_order() -> None:
    text = _read("test-layer-ownership.md")
    section = text.split("## Ownership decision", 1)[1].split("\n## ", 1)[0]
    questions = re.findall(r"^(\d)\. ", section, re.MULTILINE)
    assert questions == ["1", "2", "3", "4", "5", "6"]
    assert _in_order(
        section.lower(),
        ["static analysis", "unit test", "component test", "contract", "integration", "e2e"],
    )


def test_ownership_has_duplication_checks_removal_rule_and_in_out_of_band() -> None:
    text = _read("test-layer-ownership.md")
    for heading in (
        "## In band and out of band",
        "## What each type owns",
        "## Do not test consumed services",
        "## Duplication checks",
        "## Removal rule",
        "## Antipatterns",
    ):
        assert heading in text, heading


def test_ownership_lists_eleven_antipatterns() -> None:
    text = _read("test-layer-ownership.md")
    section = text.split("## Antipatterns", 1)[1]
    rows = [
        r
        for r in section.splitlines()
        if r.startswith("|") and not r.startswith("| Antipattern") and not re.match(r"^\|[\s:|-]+$", r)
    ]
    assert len(rows) == 11


def test_cd_test_architecture_extensions() -> None:
    text = _read("cd-test-architecture.md")
    for term in (
        "| Owns |",
        "Overlap resolution rule",
        "async handoff",
        "cross-service data consistency",
        "identity or tenant propagation",
        "deploy and config wiring",
        "third-party sandbox flow",
        "Entangled workflow candidate",
        "Critical business flow candidate",
        "synthetic monitoring",
        "test-layer-ownership.md",
        "entangled-workflows.md",
    ):
        assert term in text, term


def test_cd_test_architecture_does_not_duplicate_the_gate() -> None:
    text = _read("cd-test-architecture.md")
    assert text.count("**all four** conditions") == 1


def test_microservice_testing_contract_checks() -> None:
    text = _read("microservice-testing.md")
    section = text.split("## Contract test checks", 1)[1].split("\n## ", 1)[0]
    for term in (
        "Business-logic leak signs",
        "Weak-coverage signs",
        "Match.Type",
        "provider states",
        "no contract test",
        "no message contract",
        "no provider verification",
        "Hand-crafted fixtures",
        "unrelated domains",
        "pipeline gate",
    ):
        assert term.lower() in section.lower(), term
