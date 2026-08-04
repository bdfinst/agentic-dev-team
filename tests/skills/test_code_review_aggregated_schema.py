"""Issue #834 — aggregated --json contract defines topFindings.

The documented aggregated schema had no topFindings array and no representation
for a finding surfaced by multiple agents, so the model invented a slash-joined
severity/agent string. Bless a defined consolidated view: severity stays a
single highest-severity enum; multi-agent attribution uses an explicit
agents: [] array. This validates the blessed fixture against that shape.
"""

from __future__ import annotations

import json

from skill_doc_helpers import PLUGIN_ROOT

CODE_REVIEW_DIR = PLUGIN_ROOT / "skills" / "code-review"
FIXTURE = CODE_REVIEW_DIR / "examples" / "aggregated-sample.json"
OUTPUT_FORMAT = (CODE_REVIEW_DIR / "output-format.md").read_text(encoding="utf-8")
SKILL = (CODE_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")

ALLOWED_TOP_LEVEL = {
    "overall",
    "timestamp",
    "targetFiles",
    "preFlightPassed",
    "agents",
    "totals",
    "tokenEstimate",
    "topFindings",
    "dispatchFailures",
    "summary",
}
SEVERITY_ENUM = {"error", "warning", "suggestion"}


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_exists_and_is_valid_json():
    assert FIXTURE.is_file(), "aggregated-sample.json fixture must exist"
    _load()  # raises on invalid JSON


def test_top_level_keys_are_documented_subset():
    data = _load()
    extra = set(data) - ALLOWED_TOP_LEVEL
    assert not extra, f"undocumented top-level keys: {extra}"


def test_top_findings_severity_is_single_enum():
    data = _load()
    assert "topFindings" in data, "aggregated result must include topFindings"
    for item in data["topFindings"]:
        sev = item["severity"]
        assert sev in SEVERITY_ENUM, f"severity not a single enum: {sev!r}"
        assert "/" not in sev and "," not in sev, (
            f"severity must not be slash/comma-joined: {sev!r}"
        )


def test_top_findings_agents_is_list_of_single_tokens():
    data = _load()
    for item in data["topFindings"]:
        agents = item["agents"]
        assert isinstance(agents, list), "agents must be an array"
        assert agents, "agents array must not be empty"
        for a in agents:
            assert isinstance(a, str) and "/" not in a and "," not in a, (
                f"each agent must be a single-token string: {a!r}"
            )


def test_output_format_documents_topfindings_and_agents_array():
    assert "topFindings" in OUTPUT_FORMAT, (
        "output-format.md must document the topFindings array"
    )
    assert '"agents"' in OUTPUT_FORMAT, (
        "output-format.md must document the agents: [] array"
    )


def test_skill_step5_instructs_single_valued_cross_agent_fields():
    assert "topFindings" in SKILL, "SKILL.md step 5 must reference topFindings"
    assert "agents" in SKILL, "SKILL.md step 5 must reference the agents array"
