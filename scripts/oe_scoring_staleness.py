#!/usr/bin/env python3
"""Ownership-Engineering scoring staleness alert.

The OE judge suite (`evals/ownership-engineering/`) is scored by hand/LLM-judge,
and the result (scorecard.md + trials/) is only as current as the inputs it was
scored against. When a subject's prose, a fixture, or an `expected/*.json` changes
— or a new fixture/subject is added — the recorded scores silently go stale.

This script makes that staleness *visible*:

  --write   Snapshot the current scored inputs (subject spec files, fixtures,
            expected files) into a manifest with their SHA-256 hashes, the date,
            and the git commit. Run this right after a scoring pass.
  (default) Check the working tree against the manifest and report every
            fixture x subject pair whose inputs changed since they were scored,
            plus any new (never-scored) fixtures/subjects. Exit non-zero if any
            pair is stale (use --warn-only to always exit 0, e.g. in CI).

Inputs are model-free hashes, so the check runs anywhere with python3 + git.

Subject -> spec-file map: evals/ownership-engineering/subjects.json
Fixture -> subjects map:  the `subjects` field of each expected/*.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_DIR = REPO_ROOT / "evals" / "ownership-engineering"
MANIFEST = SUITE_DIR / "scoring-manifest.json"
SUBJECTS_MAP = SUITE_DIR / "subjects.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _load_subject_map(suite_dir: Path) -> dict[str, list[str]]:
    raw = json.loads((suite_dir / "subjects.json").read_text())
    out: dict[str, list[str]] = {}
    for name, paths in raw.items():
        if name.startswith("_"):
            continue
        out[name] = [paths] if isinstance(paths, str) else list(paths)
    return out


def scan_inputs(suite_dir: Path, repo_root: Path = REPO_ROOT) -> dict:
    """Hash every scored input the suite currently has on disk.

    Returns {"fixtures": {id: {fixture_sha, expected_sha, subjects}},
             "subjects": {name: {path: sha, ...}}}."""
    subject_map = _load_subject_map(suite_dir)
    expected_dir = suite_dir / "expected"
    fixtures_dir = suite_dir / "fixtures"

    fixtures: dict[str, dict] = {}
    for exp in sorted(expected_dir.glob("oe-*.json")):
        spec = json.loads(exp.read_text())
        fid = exp.stem  # e.g. oe-01-vague-feature-request
        fixture_md = fixtures_dir / f"{fid}.md"
        fixtures[fid] = {
            "expected_sha": _sha256(exp),
            "fixture_sha": _sha256(fixture_md) if fixture_md.exists() else None,
            "subjects": list(spec.get("subjects", [])),
        }

    subjects: dict[str, dict] = {}
    for name, paths in subject_map.items():
        files: dict[str, str | None] = {}
        for rel in paths:
            p = repo_root / rel
            files[rel] = _sha256(p) if p.exists() else None
        subjects[name] = files

    return {"fixtures": fixtures, "subjects": subjects}


def write_manifest(suite_dir: Path, manifest_path: Path, trials_per_pair: int,
                   repo_root: Path = REPO_ROOT) -> dict:
    snap = scan_inputs(suite_dir, repo_root)
    manifest = {
        "scored_at": subprocess.run(
            ["date", "+%Y-%m-%d"], capture_output=True, text=True, check=False
        ).stdout.strip() or "unknown",
        "scored_commit": _git_commit(),
        "trials_per_pair": trials_per_pair,
        **snap,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def check(suite_dir: Path, manifest_path: Path, repo_root: Path = REPO_ROOT) -> dict:
    """Diff current inputs against the manifest. Returns a structured report."""
    if not manifest_path.exists():
        return {"ok": False, "no_manifest": True, "stale": [], "new": [], "removed": []}

    manifest = json.loads(manifest_path.read_text())
    current = scan_inputs(suite_dir, repo_root)

    m_fix, c_fix = manifest.get("fixtures", {}), current["fixtures"]
    m_sub, c_sub = manifest.get("subjects", {}), current["subjects"]

    # Which subjects changed / are new, with the specific file that moved.
    subject_changed: dict[str, list[str]] = {}
    subject_new: set[str] = set()
    for name, files in c_sub.items():
        if name not in m_sub:
            subject_new.add(name)
            continue
        moved = [rel for rel, sha in files.items() if m_sub[name].get(rel) != sha]
        if moved:
            subject_changed[name] = moved

    stale: list[dict] = []
    new: list[dict] = []
    removed: list[str] = []

    for fid, cur in c_fix.items():
        subs = cur["subjects"]
        if fid not in m_fix:
            for s in subs:
                new.append({"pair": f"{fid}::{s}", "reason": "new fixture (never scored)"})
            continue
        prev = m_fix[fid]
        fixture_moved = prev.get("fixture_sha") != cur["fixture_sha"]
        expected_moved = prev.get("expected_sha") != cur["expected_sha"]
        prev_subs = set(prev.get("subjects", []))
        for s in subs:
            reasons = []
            if s not in prev_subs:
                new.append({"pair": f"{fid}::{s}", "reason": "new subject on this fixture (never scored)"})
                continue
            if fixture_moved:
                reasons.append("fixture scenario changed")
            if expected_moved:
                reasons.append("expected criteria changed")
            if s in subject_new:
                reasons.append(f"subject '{s}' not in manifest")
            elif s in subject_changed:
                reasons.append("subject prose changed: " + ", ".join(subject_changed[s]))
            if reasons:
                stale.append({"pair": f"{fid}::{s}", "reason": "; ".join(reasons)})

    for fid in m_fix:
        if fid not in c_fix:
            removed.append(fid)

    ok = not stale and not new and not removed
    return {
        "ok": ok, "no_manifest": False,
        "scored_at": manifest.get("scored_at"), "scored_commit": manifest.get("scored_commit"),
        "stale": stale, "new": new, "removed": removed,
    }


def _print_report(rep: dict) -> None:
    if rep.get("no_manifest"):
        print("OE scoring staleness: NO MANIFEST — run "
              "`python3 scripts/oe_scoring_staleness.py --write` after scoring.")
        return
    head = f"OE scoring staleness (scored_at={rep['scored_at']}, commit={rep['scored_commit']})"
    if rep["ok"]:
        print(head)
        print("OK — all scored fixture×subject pairs are current "
              "(no subject/fixture/expected changes since they were scored).")
        return
    print(head)
    if rep["stale"]:
        print(f"STALE — {len(rep['stale'])} pair(s) may be out of date and should be re-scored:")
        for item in rep["stale"]:
            print(f"  - {item['pair']}  ({item['reason']})")
    if rep["new"]:
        print(f"NEW — {len(rep['new'])} pair(s) have never been scored:")
        for item in rep["new"]:
            print(f"  - {item['pair']}  ({item['reason']})")
    if rep["removed"]:
        print(f"REMOVED — {len(rep['removed'])} scored fixture(s) no longer present:")
        for fid in rep["removed"]:
            print(f"  - {fid}")
    print("Re-run the OE judge procedure for the pairs above (see HANDOFF.md), then "
          "`python3 scripts/oe_scoring_staleness.py --write` to refresh the manifest.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="OE scoring staleness alert")
    ap.add_argument("--write", action="store_true",
                    help="snapshot current inputs into the manifest")
    ap.add_argument("--trials-per-pair", type=int, default=5,
                    help="N recorded in the manifest on --write (default 5)")
    ap.add_argument("--suite-dir", type=Path, default=SUITE_DIR)
    ap.add_argument("--repo-root", type=Path, default=REPO_ROOT,
                    help="root the subject spec paths resolve against (default: repo root)")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="manifest path (default: <suite-dir>/scoring-manifest.json)")
    ap.add_argument("--warn-only", action="store_true",
                    help="always exit 0 (print the alert but do not fail); for advisory CI use")
    ap.add_argument("--json", action="store_true", help="emit the check report as JSON")
    args = ap.parse_args(argv)

    suite_dir = args.suite_dir
    manifest_path = args.manifest or (suite_dir / "scoring-manifest.json")

    if args.write:
        m = write_manifest(suite_dir, manifest_path,
                           trials_per_pair=args.trials_per_pair,
                           repo_root=args.repo_root)
        npairs = sum(len(f["subjects"]) for f in m["fixtures"].values())
        try:
            shown = manifest_path.relative_to(REPO_ROOT)
        except ValueError:
            shown = manifest_path
        print(f"Wrote {shown} — "
              f"{len(m['fixtures'])} fixtures, {len(m['subjects'])} subjects, "
              f"{npairs} pairs @ scored_commit={m['scored_commit']}.")
        return 0

    rep = check(suite_dir, manifest_path, repo_root=args.repo_root)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        _print_report(rep)
    if args.warn_only:
        return 0
    return 0 if rep["ok"] and not rep.get("no_manifest") else 1


if __name__ == "__main__":
    sys.exit(main())
