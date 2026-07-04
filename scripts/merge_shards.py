#!/usr/bin/env python3
"""Merge per-arm shard JSONL files into the main campaign output, deduped."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARD_DIR = Path("/tmp/arm-shards")
MAIN = ROOT / "docs/experiments/data/refactor-workflow-matrix.jsonl"


def load(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def main():
    seen = {}
    for r in load(MAIN):
        key = (r.get("task"), r.get("arm"), r.get("trial"), r.get("stage"))
        seen[key] = r
    added = 0
    for shard in sorted(SHARD_DIR.glob("*.jsonl")):
        for r in load(shard):
            if r.get("stub"):
                continue
            key = (r.get("task"), r.get("arm"), r.get("trial"), r.get("stage"))
            if key not in seen:
                seen[key] = r
                added += 1
    rows = list(seen.values())
    MAIN.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"Merged: {len(rows)} total rows ({added} new from shards)")


if __name__ == "__main__":
    main()
