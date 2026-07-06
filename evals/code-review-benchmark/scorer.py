"""Hit/miss/noise scoring for the /code-review benchmark harness (#821).

A finding is a match for a ground-truth hunk when it names the same file and
its line falls within [hunk.start - tolerance, hunk.end + tolerance] — the
issue's own spec: "allow a configurable +/- N line tolerance, default 3,
since reviewers rarely flag the exact line of a fix." Every non-matching
finding is "unmatched," never "false positive" — it may be a real, different
issue the review correctly found.
"""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_TOLERANCE = 3


def _normalize_path(path: str) -> str:
    return path.lstrip("./")


def _matches(finding: Dict[str, Any], hunk: Dict[str, Any], tolerance: int) -> bool:
    if _normalize_path(str(finding.get("file", ""))) != _normalize_path(
        str(hunk.get("file", ""))
    ):
        return False
    line = finding.get("line")
    if line is None:
        return False
    start = int(hunk["start_line"]) - tolerance
    end = int(hunk["end_line"]) + tolerance
    return start <= int(line) <= end


def score(
    ground_truth_hunks: List[Dict[str, Any]],
    findings: List[Dict[str, Any]],
    tolerance: int = DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """Score one case's findings against its ground truth.

    Returns `{"hit": bool, "matched": [...], "unmatched": [...]}`. `matched`
    holds the findings that overlapped a ground-truth hunk (with the same
    finding possibly matching more than one hunk collapsed to one entry);
    `unmatched` holds every other finding, verbatim.
    """
    matched: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    for finding in findings:
        if any(_matches(finding, hunk, tolerance) for hunk in ground_truth_hunks):
            matched.append(finding)
        else:
            unmatched.append(finding)
    return {"hit": len(matched) > 0, "matched": matched, "unmatched": unmatched}
