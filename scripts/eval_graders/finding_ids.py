"""The `finding_ids` grader: did the agent report each planted defect, and nothing much else?

For agents whose output is a verdict plus lists of findings with free-text fields
(the plan critics, `gherkin-quality-critic`, `spec-reviewer`), rather than the
`status`/`issues` shape the `verdict` grader reads. Each planted defect has a stable
ID and a few keywords; a finding matches the ID when its text contains any keyword
and, if the spec names severities, its `severity` is one of them.

Spec fields (one agent block of an `evals/expected` entry)::

    statusField        output key holding the verdict (default "status")
    expectedStatus     required value of that key (omit when the agent has no verdict)
    findingFields      output keys holding finding lists; an entry is a key name or
                       {"field": key, "where": {item_key: [allowed values]}}
    expectedFindingIds [{"id", "anyOf": [keywords], "severityAnyOf": [...]?}]
    maxFindings        cap on the findings counted
    maxBySeverity      {severity: cap}
"""

from __future__ import annotations

from ._common import mentions

DEFAULT_STATUS_FIELD = "status"


def grade_finding_ids(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    fails: list[str] = []
    status_field = spec.get("statusField", DEFAULT_STATUS_FIELD)
    if "expectedStatus" in spec and actual.get(status_field) != spec["expectedStatus"]:
        fails.append(
            f"{status_field}: expected {spec['expectedStatus']!r}, "
            f"got {actual.get(status_field)!r}"
        )

    findings = collect_findings(actual, spec.get("findingFields", []))
    for expected in spec.get("expectedFindingIds", []):
        if not any(_matches(finding, expected) for finding in findings):
            fails.append(
                f"expectedFindingIds: no finding matches {expected['id']!r} "
                f"(keywords {expected.get('anyOf', [])!r})"
            )

    cap = spec.get("maxFindings")
    if cap is not None and len(findings) > cap:
        fails.append(f"maxFindings: expected at most {cap}, got {len(findings)}")
    for severity, severity_cap in spec.get("maxBySeverity", {}).items():
        count = sum(1 for finding in findings if finding.get("severity") == severity)
        if count > severity_cap:
            fails.append(
                f"maxBySeverity.{severity}: expected at most {severity_cap}, got {count}"
            )
    return fails


def collect_findings(actual: dict, finding_fields: list) -> list[dict]:
    """Every finding item named by `finding_fields`, each as a dict.

    A plain-string item becomes `{"text": item}`. Items a `where` filter excludes,
    and fields that are not lists, contribute nothing.
    """
    findings: list[dict] = []
    for field_spec in finding_fields:
        field, where = _field_and_filter(field_spec)
        items = actual.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            finding = item if isinstance(item, dict) else {"text": str(item)}
            if _passes_filter(finding, where):
                findings.append(finding)
    return findings


def _field_and_filter(field_spec) -> tuple[str, dict]:
    if isinstance(field_spec, str):
        return field_spec, {}
    return field_spec["field"], field_spec.get("where", {})


def _passes_filter(finding: dict, where: dict) -> bool:
    return all(finding.get(key) in allowed for key, allowed in where.items())


def _matches(finding: dict, expected: dict) -> bool:
    severities = expected.get("severityAnyOf")
    if severities is not None and finding.get("severity") not in severities:
        return False
    text = finding_text(finding)
    return any(mentions(text, keyword) for keyword in expected.get("anyOf", []))


def finding_text(value) -> str:
    """Every string inside `value`, joined: the text a keyword is looked for in."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(finding_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(finding_text(item) for item in value)
    return ""
