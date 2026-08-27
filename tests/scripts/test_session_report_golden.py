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
    pinning `_basename`'s cross-platform-separator fix;
  - an absolute POSIX-style file path in a third `Edit` tool_use block
    (`SENTINEL_POSIX_USER`, issue #2045), so `redact()`'s `from_path=True`
    branch is exercised against both path shapes, not Windows only; and
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

SESSION_REPORT.PY (#2046): the new unified `--profile` CLI's own golden
coverage — asserting its two profiles match these same goldens (modulo the
documented schema-version bump) — lives in the SIBLING file
`test_session_report_profiles_golden.py`, not here. That split matters for
one mechanical reason, not just organization: `session_report.py` ships
under `plugins/dev-team/scripts/` and must run on the 3.10 floor interpreter
(ADR 0031), so its test file is in `tests/repo/test_python_floor.py`'s
`FLOOR_TEST_SLICE`. This file's own `test_session_extract_matches_golden`
imports `scripts/session_extract.py`, a monorepo-only script that legitimately
uses `datetime.UTC` (3.11+) because it is NOT subject to that floor — mixing
the two in one file would have made the floor gate fail on an unrelated,
by-design exemption the instant this file joined its test slice.
"""

from __future__ import annotations

import json

from _session_report_golden_fixtures import (
    CORPUS_ROOT,
    EXTRACT_SESSION_REPORT_GOLDEN,
    EXTRACT_SESSION_REPORT_SCRIPT,
    PLUGIN_VERSION,
    PRICING,
    REGISTRY,
    SENTINELS,
    SESSION_EXTRACT_GOLDEN,
    SESSION_EXTRACT_SCRIPT,
    load_module,
)


def _session_extract_digest() -> dict:
    module = load_module(SESSION_EXTRACT_SCRIPT, "_golden_session_extract")
    paths = module._all_transcripts_under(CORPUS_ROOT)
    return module.extract(
        paths,
        PRICING,
        REGISTRY,
        plugin_version=PLUGIN_VERSION,
        projects_root=CORPUS_ROOT,
    )


def _extract_session_report_digest() -> dict:
    module = load_module(EXTRACT_SESSION_REPORT_SCRIPT, "_golden_extract_session_report")
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
