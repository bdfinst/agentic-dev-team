#!/usr/bin/env python3
"""Update docs/experiments/05-status.md with current campaign progress."""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs/experiments/data/refactor-workflow-matrix.jsonl"
STATUS = ROOT / "docs/experiments/05-status.md"
CAMPAIGN_START = datetime.fromisoformat("2026-06-27T02:50:58.627370+00:00")
ALL_ARMS = {
    "tdd-refactor", "continuous-single", "continuous-split",
    "one-shot-single", "one-shot-split",
    "all-tests-first-single", "all-tests-first-split",
}
TASKS = ["fare", "payroll", "cart", "grades"]


def icon(n):
    if n == 7:
        return "✅ done"
    if n > 0:
        return "🔄 in progress"
    return "⏳ queued"


def main():
    if not DATA.exists():
        print("Data file not found — skipping update.", file=sys.stderr)
        return

    rows = [json.loads(l) for l in DATA.read_text().splitlines() if l.strip()]
    by_task = defaultdict(set)
    for r in rows:
        by_task[r["task"]].add(r["arm"])

    total = len(rows)
    base_total = 672
    pct = 100 * total // base_total

    now = datetime.now(timezone.utc)
    elapsed = now - CAMPAIGN_START
    h, rem = divmod(int(elapsed.total_seconds()), 3600)
    m = rem // 60
    elapsed_str = f"{h}h {m}m"

    task_rows = "\n".join(
        f"| {t} | {len(by_task.get(t, set()))} / 7 | {icon(len(by_task.get(t, set())))} |"
        for t in TASKS
    )

    block = (
        f"**Overall:** {total} / {base_total} rows written — **{pct}% complete**\n"
        f"\n"
        f"| Task | Arms complete | Status |\n"
        f"|---|---|---|\n"
        f"{task_rows}\n"
        f"\n"
        f"_Base campaign: 7 arms × 4 tasks × 6 trials = 168 cells × 4 rows = 672 rows. "
        f"Sequential extension may add more._\n"
        f"\n"
        f"**Campaign started:** 2026-06-27 02:50 UTC — **elapsed: {elapsed_str}**"
    )

    text = STATUS.read_text()
    # Update last-updated line
    text = re.sub(
        r"\*\*Last updated:\*\*.*",
        f"**Last updated:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
        text,
    )
    # Replace status block
    text = re.sub(
        r"<!-- STATUS_START -->.*?<!-- STATUS_END -->",
        f"<!-- STATUS_START -->\n{block}\n<!-- STATUS_END -->",
        text,
        flags=re.DOTALL,
    )
    STATUS.write_text(text)
    print(f"Updated: {total}/{base_total} rows ({pct}%), elapsed {elapsed_str}")


if __name__ == "__main__":
    main()
