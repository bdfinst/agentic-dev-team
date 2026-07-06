"""The `verdict` grader (issue #309).

This is the original `grade_agent` path lifted verbatim out of the monolith: it
grades a single review agent's recorded verdict (status, issue counts, severity
buckets, keyword presence/absence) against its expected JSON. It is the default
grader for entries in an expected file's `agents` block, so existing fixtures
grade byte-for-byte identically.
"""

from __future__ import annotations

from ._common import in_range, mentions


def grade_verdict(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    fails: list[str] = []

    exp_status = spec.get("expectedStatus")
    got_status = actual.get("status")
    if exp_status is not None and got_status != exp_status:
        fails.append(f"status: expected {exp_status!r}, got {got_status!r}")

    issues = actual.get("issues", []) or []
    if "issueCount" in spec and not in_range(len(issues), spec["issueCount"]):
        rng = spec["issueCount"]
        fails.append(
            f"issueCount: expected {rng.get('min', 0)}-{rng.get('max', '∞')}, "
            f"got {len(issues)}"
        )

    for sev, rng in spec.get("severities", {}).items():
        count = sum(1 for i in issues if i.get("severity") == sev)
        if not in_range(count, rng):
            fails.append(
                f"severities.{sev}: expected {rng.get('min', 0)}-"
                f"{rng.get('max', '∞')}, got {count}"
            )

    # `minConfidenceAnyOf` (issue #885): assert at least one issue carries a
    # confidence in the given set — used by fixtures that require the agent
    # to flag a known defect at high-or-medium confidence without pinning an
    # exact count (an agent may reasonably report the same defect more than
    # once, or bundle it with a related finding).
    min_conf = spec.get("minConfidenceAnyOf")
    if min_conf and not any(i.get("confidence") in min_conf for i in issues):
        fails.append(
            f"minConfidenceAnyOf: expected at least one issue with "
            f"confidence in {min_conf!r}, found none"
        )

    text = " ".join(str(i.get("message", "")) for i in issues)
    text += " " + str(actual.get("summary", ""))
    for kw in spec.get("mustMention", []):
        if not mentions(text, kw):
            fails.append(f"mustMention: missing {kw!r}")
    for kw in spec.get("mustNotMention", []):
        if mentions(text, kw):
            fails.append(f"mustNotMention: found forbidden {kw!r}")

    return fails
