"""Golden-file regression harness for the two forked session-transcript
extractors (issue #2041, the first slice of epic #2040).

WHY: `scripts/session_extract.py` and
`plugins/dev-team/scripts/extract_session_report.py` are deliberately forked,
with known-drifted behavior — see
`docs/adr/0036-the-two-session-extractors-stay-forked-1994.md`. Nothing in
#2040's eventual reconciliation may move until there is a mechanism that
fails the instant either script's reported numbers change by a single byte.
This module is that mechanism: it is pure test infrastructure and makes no
behavior change to either script.

CORPUS: `tests/fixtures/session_log/projects/` is a committed, synthetic
transcript tree (fabricated, never real session data) covering:

  - a main-thread session with full `usage` accounting (input, output,
    `cache_creation_input_tokens`, `cache_read_input_tokens`);
  - a record with a missing `usage` key, and one with `usage: null` — the
    two shapes the null-handling idiom in both scripts' `extract()` must
    treat identically;
  - a plain Agent-dispatch subagent transcript
    (`subagents/agent-aaa1.jsonl`, `attributionAgent` set);
  - a Workflow-dispatch subagent transcript nested one level deeper
    (`subagents/workflows/review-panel/agent-bbb2.jsonl`) — the layout
    issue #1990 was originally blind to;
  - a subagent transcript with no `attributionAgent` at all
    (`subagents/agent-ccc3.jsonl`) — the `unattributed` bucket;
  - a Windows-style backslash file path in two `Edit` tool_use blocks,
    pinning `_basename`'s cross-platform-separator fix; and
  - sentinel prompt/code/command strings (`SENTINEL_..._DO_NOT_LEAK`) that
    must never appear in either script's output.

INVOCATION: both scripts' `extract()` — the function each script's own test
suite already exercises directly and via CLI (see
`tests/scripts/test_extract_session_report.py` and
`tests/repo/test_session_extract_subagents.py`) — is called DIRECTLY via
`importlib`, not through either script's CLI `main()`. `main()` bakes in the
wall clock (`generated_at`), the machine hostname, and — for the shipped
script specifically — the live repo's OWN agents/skills registry and
`.claude-plugin/plugin.json` version. A golden keyed to any of those would
fail on a release version bump or an unrelated skill being added elsewhere
in the repo, for reasons having nothing to do with either extractor's own
accumulation logic. Calling `extract()` directly with a fixed, literal
`registry` dict (and, for `session_extract.py`, a fixed `pricing` dict and
`plugin_version` string) isolates the golden to exactly what issue #2041 is
chartered to protect.

REGENERATING GOLDENS: an intended behavior change must be a reviewable
`git diff` on the `.golden.json` files, not a hand-edit. Regenerate with:

    python3 tests/scripts/test_session_report_golden.py

then re-run this file under pytest and review the resulting `git diff`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

# Under pytest, pytest.ini's `pythonpath = .` already makes `_repo_root`
# importable. The regeneration entry point at the bottom of this file runs as
# `python3 tests/scripts/test_session_report_golden.py` instead, with no such
# pythonpath — so make the repo root importable here too, before relying on it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _repo_root import REPO_ROOT

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "session_log"
CORPUS_ROOT = FIXTURE_ROOT / "projects"

SESSION_EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "session_extract.py"
EXTRACT_SESSION_REPORT_SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "extract_session_report.py"

SESSION_EXTRACT_GOLDEN = FIXTURE_ROOT / "session_extract.golden.json"
EXTRACT_SESSION_REPORT_GOLDEN = FIXTURE_ROOT / "extract_session_report.golden.json"

# Fixed, literal registry — deliberately NOT the live plugin's agents/skills
# dirs (see module docstring). Names match the corpus's `attributionAgent`
# values (stripped of their `dev-team:` namespace) plus one never-invoked
# agent/skill each, so `never_observed_*` has non-trivial content.
REGISTRY = {
    "skills": ["never-invoked-skill"],
    "agents": ["correctness-review", "doc-review", "never-invoked-agent"],
}

# session_extract.py-only: a fixed pricing table so `token.cost_usd` is a
# deterministic function of the corpus, independent of the shipped
# knowledge/model-pricing.json (which changes for reasons unrelated to this
# harness).
PRICING = {
    "models": {"claude-sonnet-5": {"input": 3.0, "output": 15.0}},
    "cache_write_multiplier": 1.25,
    "cache_read_multiplier": 0.1,
}
PLUGIN_VERSION = "0.0.0-golden"

# Sentinel markers embedded in the corpus (see fixture files under
# tests/fixtures/session_log/projects/) that must never surface in either
# script's output.
SENTINELS = (
    "SENTINEL_PROMPT_DO_NOT_LEAK",
    "SENTINEL_CODE_DO_NOT_LEAK",
    "SENTINEL_CMD_do_not_leak",
    "SENTINEL_USER",
)


def _load_module(path: Path, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session_extract_digest() -> dict:
    module = _load_module(SESSION_EXTRACT_SCRIPT, "_golden_session_extract")
    paths = module._all_transcripts_under(CORPUS_ROOT)
    return module.extract(
        paths,
        PRICING,
        REGISTRY,
        plugin_version=PLUGIN_VERSION,
        projects_root=CORPUS_ROOT,
    )


def _extract_session_report_digest() -> dict:
    module = _load_module(EXTRACT_SESSION_REPORT_SCRIPT, "_golden_extract_session_report")
    paths = module._all_transcripts(CORPUS_ROOT)
    return module.extract(paths, REGISTRY, CORPUS_ROOT)


def _dump(digest: dict) -> str:
    return json.dumps(digest, indent=2, sort_keys=True) + "\n"


def test_session_extract_matches_golden():
    actual = _dump(_session_extract_digest())
    expected = SESSION_EXTRACT_GOLDEN.read_text(encoding="utf-8")
    assert actual == expected, (
        "scripts/session_extract.py's extract() output changed — see module "
        "docstring for how to review and regenerate the golden."
    )


def test_extract_session_report_matches_golden():
    actual = _dump(_extract_session_report_digest())
    expected = EXTRACT_SESSION_REPORT_GOLDEN.read_text(encoding="utf-8")
    assert actual == expected, (
        "plugins/dev-team/scripts/extract_session_report.py's extract() "
        "output changed — see module docstring for how to review and "
        "regenerate the golden."
    )


def test_no_sentinel_leaks_in_either_golden():
    for golden in (SESSION_EXTRACT_GOLDEN, EXTRACT_SESSION_REPORT_GOLDEN):
        raw = golden.read_text(encoding="utf-8")
        for sentinel in SENTINELS:
            assert sentinel not in raw, f"{sentinel!r} leaked into {golden.name}"


def _regenerate() -> None:
    SESSION_EXTRACT_GOLDEN.write_text(_dump(_session_extract_digest()), encoding="utf-8")
    EXTRACT_SESSION_REPORT_GOLDEN.write_text(
        _dump(_extract_session_report_digest()), encoding="utf-8"
    )
    print(f"wrote {SESSION_EXTRACT_GOLDEN}")
    print(f"wrote {EXTRACT_SESSION_REPORT_GOLDEN}")


if __name__ == "__main__":
    _regenerate()
