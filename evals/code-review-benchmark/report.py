"""Report generator for the /code-review benchmark harness (#821).

Reads `results.jsonl` (+ `skipped.jsonl`) and writes `report.md`: overall and
per-dataset/per-project recall, a dedicated Missed Defects section (the
issue's explicit "actionable part I actually want to read"), and a noise
summary so the operator can eyeball whether the flow is
quiet-and-precise or noisy-and-broad.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return records


def _recall(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    records = list(records)
    attempted = len(records)
    hits = sum(1 for r in records if r.get("hit"))
    return {
        "attempted": attempted,
        "hits": hits,
        "recall": (hits / attempted) if attempted else None,
    }


def _group_by(
    records: List[Dict[str, Any]], key: str
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        grouped[r.get(key, "unknown")].append(r)
    return grouped


def _fmt_recall(stats: Dict[str, Any]) -> str:
    if stats["recall"] is None:
        return "n/a (0 attempted)"
    return f"{stats['hits']}/{stats['attempted']} ({stats['recall']:.0%})"


def build_report(results_dir: Any) -> str:
    """Build the report.md text from `results_dir`'s results.jsonl/skipped.jsonl."""
    results_dir = Path(results_dir)
    results = _read_jsonl(results_dir / "results.jsonl")
    skipped = _read_jsonl(results_dir / "skipped.jsonl")

    lines: List[str] = ["# /code-review Benchmark Report", ""]

    overall = _recall(results)
    lines.append(f"Overall recall: {_fmt_recall(overall)}")
    if skipped:
        lines.append(f"Skipped: {len(skipped)} (see Skipped section below)")
    lines.append("")

    lines.append("## Recall by dataset")
    lines.append("")
    lines.append("| Dataset | Hits | Attempted | Recall |")
    lines.append("| --- | --- | --- | --- |")
    for dataset, recs in sorted(_group_by(results, "dataset").items()):
        stats = _recall(recs)
        lines.append(
            f"| {dataset} | {stats['hits']} | {stats['attempted']} | "
            f"{stats['recall']:.0%} |"
            if stats["recall"] is not None
            else f"| {dataset} | 0 | 0 | n/a |"
        )
    lines.append("")

    lines.append("## Recall by project")
    lines.append("")
    lines.append("| Dataset | Project | Hits | Attempted | Recall |")
    lines.append("| --- | --- | --- | --- | --- |")
    by_project: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_project[(r.get("dataset"), r.get("project"))].append(r)
    for (dataset, project), recs in sorted(by_project.items()):
        stats = _recall(recs)
        recall_str = f"{stats['recall']:.0%}" if stats["recall"] is not None else "n/a"
        lines.append(
            f"| {dataset} | {project} | {stats['hits']} | {stats['attempted']} | {recall_str} |"
        )
    lines.append("")

    lines.append("## Missed Defects")
    lines.append("")
    misses = [r for r in results if not r.get("hit")]
    if not misses:
        lines.append("None — every attempted bug was hit.")
    else:
        for r in misses:
            hunks = r.get("ground_truth_hunks") or []
            location = "; ".join(
                f"{h.get('file')}:{h.get('start_line')}-{h.get('end_line')}"
                for h in hunks
            )
            lines.append(
                f"### {r.get('dataset')} / {r.get('project')} / bug {r.get('bug_id')}"
            )
            lines.append("")
            lines.append(f"- Ground truth: {location or 'unknown'}")
            if r.get("description"):
                lines.append(f"- Description: {r.get('description')}")
            lines.append(f"- Raw output: {r.get('raw_output_path')}")
            lines.append("")
    lines.append("")

    lines.append("## Noise summary")
    lines.append("")
    hit_records = [r for r in results if r.get("hit")]
    if hit_records:
        avg_unmatched = sum(
            len(r.get("unmatched_findings") or []) for r in hit_records
        ) / len(hit_records)
        lines.append(f"Average unmatched findings per hit run: {avg_unmatched:.1f}")
    else:
        lines.append("No hit runs to compute noise from.")
    lines.append("")

    if skipped:
        lines.append("## Skipped")
        lines.append("")
        for s in skipped:
            lines.append(
                f"- {s.get('dataset')} / {s.get('project')} / bug {s.get('bug_id')}: "
                f"{s.get('reason')}"
            )
        lines.append("")

    return "\n".join(lines)


def write_report(results_dir: Any) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    report_text = build_report(results_dir)
    report_path = results_dir / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    return report_path


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "evals/code-review-benchmark/results"
    path = write_report(target)
    print(f"Wrote {path}")
