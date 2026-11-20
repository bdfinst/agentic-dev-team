"""The `verdict` grader.

It grades a single review agent's recorded verdict (status, issue counts, severity
buckets, keyword presence/absence) against its expected JSON. It is the default
grader for entries in an expected file's `agents` block, so existing fixtures
grade byte-for-byte identically.
"""

from __future__ import annotations

from ._common import in_range, mentions


def _tolerated_suggestion_warn(spec: dict, status, issues: list) -> bool:
    """True when a `pass` expectation meets a `warn` made only of tolerated suggestions.

    The output contract sets `pass` to zero issues and `warn` to issues with no
    error, so an agent that reports one suggestion must say `warn`. A clean
    entry that pairs `expectedStatus: pass` with an `issueCount` window above
    zero tolerates such suggestions; without this rule that window could never
    be met. The `issueCount` check still bounds how many are tolerated. A
    window with no `max` is unbounded, as in `in_range`; an entry with no
    `issueCount` at all tolerates nothing.
    """
    if "issueCount" not in spec:
        return False
    return (
        spec.get("expectedStatus") == "pass"
        and status == "warn"
        and len(issues) > 0
        and in_range(len(issues), spec["issueCount"])
        and all(i.get("severity") == "suggestion" for i in issues)
    )


def grade_verdict(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    fails: list[str] = []

    issues = actual.get("issues", []) or []
    exp_status = spec.get("expectedStatus")
    got_status = actual.get("status")
    if (
        exp_status is not None
        and got_status != exp_status
        and not _tolerated_suggestion_warn(spec, got_status, issues)
    ):
        fails.append(f"status: expected {exp_status!r}, got {got_status!r}")

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

    # `expectedFindings` (#2283): the set of (category, severity) pairs the
    # agent reports must equal the declared set exactly. For agents whose
    # `category` is a stable rule id (sql-review), this pins WHICH rule fired
    # at WHICH severity, which a count range cannot.
    expected_findings = spec.get("expectedFindings")
    if expected_findings is not None:
        want = {(f.get("category"), f.get("severity")) for f in expected_findings}
        got = {(i.get("category"), i.get("severity")) for i in issues}
        if want != got:
            fails.append(
                f"expectedFindings: expected {sorted(want, key=repr)!r}, "
                f"got {sorted(got, key=repr)!r}"
            )

    # An issue's `smell` (test-smell-review) or `category` names the finding as
    # much as its message does, so each counts toward what the agent mentioned.
    text = " ".join(
        f"{i.get('smell', '')} {i.get('category', '')} {i.get('message', '')}"
        for i in issues
    )
    text += " " + str(actual.get("summary", ""))
    for kw in spec.get("mustMention", []):
        if not mentions(text, kw):
            fails.append(f"mustMention: missing {kw!r}")
    # `mustNotMention` asks "did the agent report this?", so it reads the issues
    # only. The summary may name a smell to say it does not apply ("not a
    # Contract Business-Logic Leak"), which is a correct pass, not a report.
    reported = " ".join(
        f"{i.get('smell', '')} {i.get('category', '')} {i.get('message', '')}"
        for i in issues
    )
    for kw in spec.get("mustNotMention", []):
        if mentions(reported, kw):
            fails.append(f"mustNotMention: found forbidden {kw!r}")

    return fails
