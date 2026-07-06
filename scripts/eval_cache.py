#!/usr/bin/env python3
"""Per-pair fingerprint replay cache for the live eval gate (issue #311).

Every live eval run pays full token cost for each ``fixture::agent`` pair even
when nothing that could change the verdict has changed since the last green run.
That is the proximate reason the live gate stays opt-in. This module makes the
live gate economical (and so eligible to go default-on) by fingerprinting each
pair and replaying a prior PASS at zero cost when the fingerprint is unchanged.

Fingerprint
-----------
For a pair ``<stem>::<target>`` the SHA-256 is computed over, in order:

  1. the resolved model identity the pair was (or will be) graded under
     (``--model``; see below),
  2. the target's root definition (agent ``agents/<t>.md`` or skill
     ``skills/<t>/SKILL.md``),
  3. the **transitive closure** of dependency files reachable from it
     (``knowledge/*.md`` it reads, ``skills/*`` it invokes — recursively),
  4. the fixture file(s) for the stem,
  5. the expected JSON,
  6. the grader version (hash of the eval_graders package sources).

Any change to any contributing input changes the SHA, which busts the cache and
forces a live dispatch. An unchanged SHA with a stored PASS replays.

Model dimension (#881, band calibration slice 2)
-------------------------------------------------
The fingerprint includes the resolved model identity (``--model``, e.g.
``claude-sonnet-4-6``), so a PASS memoized for one model never replays for a
different model — each model's per-band calibration results memoize
independently. ``--model`` defaults to ``"unspecified"`` when the caller does
not pass one (all such callers share that one bucket). Because this dimension
is new, every cache entry written before this change busts exactly once on
first replay attempt after upgrade — there is no stored model to compare
against, so the recomputed SHA (which now folds in a model) never matches the
old stored SHA (which never did). This is a one-time, self-healing cost: the
next ``--store`` re-populates the entry with a model-aware SHA and it replays
normally from then on.

Cache
-----
``evals/.eval-cache.json`` (gitignored). Corruption is silently ignored — a
bad cache degrades to a full live dispatch, never an error.

CLI
---
``--fingerprint <pair>``   print the SHA and the contributing file list.
``--plan``                 classify every corpus pair (filtered by --only) into
                           cache hits (replayable) and misses (need dispatch);
                           write a plan JSON and a prefilled replay actuals file.
``--store --actuals F``    grade F and write each PASSing pair to the cache with
                           its current fingerprint and full actuals.
``--model M``              resolved model identity to fold into the fingerprint
                           (default "unspecified"); applies to --fingerprint,
                           --plan and --store alike.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_grade import run_grading  # noqa: E402

CACHE_VERSION = 1
# References we follow when walking an agent/skill/knowledge file for deps.
_KNOWLEDGE_RE = re.compile(r"knowledge/([A-Za-z0-9_-]+)\.md")
_SKILL_PATH_RE = re.compile(r"skills/([A-Za-z0-9_-]+)/")
_SKILL_TOOL_RE = re.compile(r"Skill\(([A-Za-z0-9_-]+)")


class Dirs:
    """Resolved repo locations; overridable so tests run on a tmp corpus."""

    def __init__(self, repo_root: Path, expected_dir: Path | None = None,
                 fixtures_dir: Path | None = None,
                 plugin_root: Path | None = None):
        self.repo_root = repo_root
        self.expected = expected_dir or repo_root / "evals" / "expected"
        self.fixtures = fixtures_dir or repo_root / "evals" / "fixtures"
        self.plugin = plugin_root or repo_root / "plugins" / "dev-team"
        self.agents = self.plugin / "agents"
        self.skills = self.plugin / "skills"
        self.knowledge = self.plugin / "knowledge"
        self.graders = Path(__file__).resolve().parent / "eval_graders"


def grader_version(graders_dir: Path) -> str:
    """SHA-256 over the grader package sources — bumps when grading logic moves."""
    h = hashlib.sha256()
    for src in sorted(graders_dir.glob("*.py")):
        h.update(src.name.encode())
        h.update(b"\0")
        h.update(src.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def resolve_root_file(pair: str, dirs: Dirs):
    """Return (block, Path|None) for the target's root definition.

    ``block`` is "agents" or "skills" depending on where the target is declared
    in its expected JSON; the path is the agent .md or skill SKILL.md.
    """
    stem, _, target = pair.partition("::")
    spec_path = dirs.expected / f"{stem}.json"
    block = None
    if spec_path.exists():
        try:
            spec = json.loads(spec_path.read_text())
            if target in spec.get("agents", {}):
                block = "agents"
            elif target in spec.get("skills", {}):
                block = "skills"
        except json.JSONDecodeError:
            pass
    agent_md = dirs.agents / f"{target}.md"
    skill_md = dirs.skills / target / "SKILL.md"
    if block == "skills" and skill_md.exists():
        return "skills", skill_md
    if block == "agents" and agent_md.exists():
        return "agents", agent_md
    # Fall back to whichever file exists (block undeclared / spec unreadable).
    if agent_md.exists():
        return "agents", agent_md
    if skill_md.exists():
        return "skills", skill_md
    return block, None


def transitive_deps(root_file: Path, dirs: Dirs) -> list[Path]:
    """Sorted, de-duplicated closure of dep files reachable from root_file.

    Follows ``knowledge/<n>.md`` reads, ``skills/<n>/`` paths and ``Skill(<n>``
    invocations recursively. Only existing files are returned; the root file
    itself is excluded (the caller hashes it separately).
    """
    seen: set[Path] = set()
    stack = [root_file]
    visited_text: set[Path] = set()
    while stack:
        cur = stack.pop()
        if cur in visited_text or not cur.exists():
            continue
        visited_text.add(cur)
        try:
            text = cur.read_text()
        except OSError:
            continue
        names = set()
        for m in _KNOWLEDGE_RE.finditer(text):
            kf = dirs.knowledge / f"{m.group(1)}.md"
            if kf.exists() and kf not in seen:
                seen.add(kf)
                stack.append(kf)
        for rex in (_SKILL_PATH_RE, _SKILL_TOOL_RE):
            for m in rex.finditer(text):
                names.add(m.group(1))
        for name in names:
            sf = dirs.skills / name / "SKILL.md"
            if sf.exists() and sf != root_file and sf not in seen:
                seen.add(sf)
                stack.append(sf)
    return sorted(seen)


def resolve_fixture_files(stem: str, spec: dict, dirs: Dirs) -> list[Path]:
    """Fixture file(s) for a stem — the named file, or every file in a dir."""
    candidates = []
    fixture = spec.get("fixture")
    if fixture:
        candidates.append(dirs.fixtures / fixture)
    candidates.append(dirs.fixtures / stem)  # directory fixtures use the stem
    for cand in candidates:
        if cand.is_file():
            return [cand]
        if cand.is_dir():
            return sorted(p for p in cand.rglob("*") if p.is_file())
    return []


def contributing_files(pair: str, dirs: Dirs) -> list[Path]:
    """Ordered list of every file whose content feeds the fingerprint."""
    stem, _, _ = pair.partition("::")
    spec_path = dirs.expected / f"{stem}.json"
    spec = {}
    if spec_path.exists():
        try:
            spec = json.loads(spec_path.read_text())
        except json.JSONDecodeError:
            spec = {}
    files: list[Path] = []
    _, root = resolve_root_file(pair, dirs)
    if root:
        files.append(root)
        files.extend(transitive_deps(root, dirs))
    files.extend(resolve_fixture_files(stem, spec, dirs))
    if spec_path.exists():
        files.append(spec_path)
    # De-dup, preserve order.
    seen: set[Path] = set()
    ordered = []
    for f in files:
        if f not in seen:
            seen.add(f)
            ordered.append(f)
    return ordered


DEFAULT_MODEL = "unspecified"


def compute_fingerprint(pair: str, dirs: Dirs, model: str = DEFAULT_MODEL):
    """Return (sha_hex, [relative file strings]) for a pair.

    ``model`` is the resolved model identity the pair is graded under (#881).
    It is folded into the SHA as its own dimension so a PASS memoized at one
    model is never treated as a hit for a different model.
    """
    files = contributing_files(pair, dirs)
    h = hashlib.sha256()
    h.update(f"model:{model}\0".encode())
    h.update(f"grader:{grader_version(dirs.graders)}\0".encode())
    rels: list[str] = []
    for f in files:
        try:
            rel = str(f.relative_to(dirs.repo_root))
        except ValueError:
            rel = str(f)
        rels.append(rel)
        h.update(rel.encode())
        h.update(b"\0")
        try:
            h.update(f.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest(), rels


# --------------------------------------------------------------------------
# Cache I/O — corruption is never fatal.
# --------------------------------------------------------------------------

def load_cache(path: Path) -> dict:
    """Load the cache; any error (missing, corrupt, wrong shape) -> empty."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"version": CACHE_VERSION, "entries": {}}
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        return {"version": CACHE_VERSION, "entries": {}}
    return data


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def cache_get(cache: dict, pair: str, sha: str):
    """Return the stored actual for a replayable hit, else None.

    A hit requires the stored fingerprint to match AND the stored result to be a
    PASS — a cached failure is never replayed (it must be re-dispatched).
    """
    entry = cache.get("entries", {}).get(pair)
    if not entry or entry.get("sha") != sha or not entry.get("passed"):
        return None
    return entry.get("actual")


def cache_put(cache: dict, pair: str, sha: str, actual: dict, model: str = DEFAULT_MODEL) -> None:
    from datetime import datetime, timezone
    cache.setdefault("entries", {})[pair] = {
        "sha": sha,
        "passed": True,
        "actual": actual,
        "model": model,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# --------------------------------------------------------------------------
# Pair enumeration over the corpus.
# --------------------------------------------------------------------------

def corpus_pairs(dirs: Dirs, only: set | None):
    """Yield (pair, block) for every gradable target in the expected corpus."""
    for ef in sorted(dirs.expected.glob("*.json")):
        try:
            spec = json.loads(ef.read_text())
        except json.JSONDecodeError:
            continue
        stem = ef.stem
        for block in ("agents", "skills"):
            for name in spec.get(block, {}):
                if only and name not in only:
                    continue
                yield f"{stem}::{name}", block


def _split_actual(actuals_entry_block: dict, block: str, name: str):
    return actuals_entry_block.get(block, {}).get(name)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--expected-dir")
    ap.add_argument("--fixtures-dir")
    ap.add_argument("--plugin-root")
    ap.add_argument("--cache", help="cache file (default: <repo>/evals/.eval-cache.json)")
    ap.add_argument("--only", default="",
                    help="comma-separated agent/skill names to scope to")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="resolved model identity (#881) — a fingerprint dimension; "
                         f"defaults to {DEFAULT_MODEL!r} when omitted")
    ap.add_argument("--fingerprint", metavar="PAIR",
                    help="print the SHA + contributing files for <stem>::<target>")
    ap.add_argument("--plan", action="store_true",
                    help="classify corpus pairs into cache hits/misses")
    ap.add_argument("--plan-out", help="write the plan JSON here")
    ap.add_argument("--replay-out",
                    help="write prefilled replay actuals (cache hits) here")
    ap.add_argument("--store", action="store_true",
                    help="grade --actuals and store PASSing pairs to the cache")
    ap.add_argument("--actuals", help="actuals.json (with --store)")
    ap.add_argument("--baseline", help="baseline.json (with --store, optional)")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    dirs = Dirs(
        repo_root,
        Path(args.expected_dir).resolve() if args.expected_dir else None,
        Path(args.fixtures_dir).resolve() if args.fixtures_dir else None,
        Path(args.plugin_root).resolve() if args.plugin_root else None,
    )
    cache_path = Path(args.cache) if args.cache else repo_root / "evals" / ".eval-cache.json"
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    if args.fingerprint:
        sha, files = compute_fingerprint(args.fingerprint, dirs, args.model)
        print(f"pair:        {args.fingerprint}")
        print(f"model:       {args.model}")
        print(f"fingerprint: {sha}")
        print(f"grader:      {grader_version(dirs.graders)[:16]}…")
        print("contributing files:")
        for f in files:
            print(f"  - {f}")
        if not files:
            print("  (none found — unknown target/stem; live dispatch always)")
        return 0

    if args.plan:
        cache = load_cache(cache_path)
        hits, misses, fingerprints = {}, [], {}
        for pair, block in corpus_pairs(dirs, only):
            sha, _ = compute_fingerprint(pair, dirs, args.model)
            fingerprints[pair] = sha
            actual = cache_get(cache, pair, sha)
            if actual is not None:
                hits[pair] = {"block": block, "actual": actual}
            else:
                misses.append(pair)
        plan = {
            "hits": sorted(hits),
            "misses": sorted(misses),
            "fingerprints": fingerprints,
        }
        if args.plan_out:
            Path(args.plan_out).write_text(json.dumps(plan, indent=2) + "\n")
        if args.replay_out:
            replay: dict = {}
            for pair, info in hits.items():
                stem, _, name = pair.partition("::")
                replay.setdefault(stem, {}).setdefault(info["block"], {})[name] = info["actual"]
            Path(args.replay_out).write_text(json.dumps(replay, indent=2) + "\n")
        print(f"plan: {len(hits)} cache hit(s) replayable, {len(misses)} miss(es) "
              f"need live dispatch.")
        for pair in sorted(misses):
            print(f"  · miss {pair}")
        return 0

    if args.store:
        if not args.actuals:
            print("error: --store needs --actuals", file=sys.stderr)
            return 2
        try:
            actuals = json.loads(Path(args.actuals).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read actuals: {exc}", file=sys.stderr)
            return 2
        baseline = None
        if args.baseline and Path(args.baseline).exists():
            baseline = json.loads(Path(args.baseline).read_text())
        results, _ = run_grading(dirs.expected, actuals, baseline, only)
        cache = load_cache(cache_path)
        stored = 0
        for pair, passed, _fails in results:
            if not passed:
                continue
            stem, _, name = pair.partition("::")
            entry = actuals.get(stem, {})
            actual = entry.get("agents", {}).get(name)
            if actual is None:
                actual = entry.get("skills", {}).get(name)
            if actual is None:
                continue
            sha, _ = compute_fingerprint(pair, dirs, args.model)
            cache_put(cache, pair, sha, actual, args.model)
            stored += 1
        save_cache(cache_path, cache)
        print(f"cache: stored {stored} passing pair(s) → {cache_path}")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
