"""Golden-file regression harness for `session_report.py`'s two profiles
(issue #2041, epic #2040).

WHY: `session_report.py --profile maintainer|downstream` replaces two
scripts that were deliberately forked, with known-drifted behavior — see
`docs/adr/0036-the-two-session-extractors-stay-forked-1994.md` (superseded).
This module is the mechanism that fails the instant either profile's
reported numbers change by a single byte.

HISTORY: through #2047, this file golden-tested the two now-retired
predecessor scripts directly, and a sibling file
(`test_session_report_profiles_golden.py`) golden-tested session_report.py
against those same goldens modulo a documented schema-version bump. The
split existed for one mechanical reason: `session_report.py` ships under
`plugins/dev-team/scripts/` and is subject to the 3.10 floor interpreter
(ADR 0031), while the retired maintainer predecessor legitimately used
`datetime.UTC` (3.11+, out of the floor's scope) — mixing the two in one
file would have failed the floor gate on an unrelated, by-design exemption.
#2048 deleted both predecessors, so that reason is gone: this file is
merged back into one, and the two `.golden.json` fixtures below now state
their PERMANENT `v3` schema value directly rather than being patched at
assertion time against a stale `v2` literal.

CORPUS: `tests/fixtures/session_log/projects/` is a committed, synthetic
transcript tree (fabricated, never real session data) covering:

  - a main-thread session with full `usage` accounting (input, output,
    `cache_creation_input_tokens`, `cache_read_input_tokens`);
  - a record with a missing `usage` key, and one with `usage: null` — the
    two shapes the null-handling idiom in both profiles' extract functions
    must treat identically;
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
    must never appear in either profile's output.

INVOCATION: `extract_maintainer()`/`extract_downstream()` — the functions
`test_extract_session_report.py` and `test_session_extract_subagents.py`
already exercise directly and via CLI — are called DIRECTLY via `importlib`,
not through `session_report.py`'s CLI `main()`. `main()` bakes in the wall
clock (`generated_at`), the machine hostname, and — for the maintainer
profile specifically — the live repo's OWN agents/skills registry and
`.claude-plugin/plugin.json` version. A golden keyed to any of those would
fail on a release version bump or an unrelated skill being added elsewhere
in the repo, for reasons having nothing to do with either profile's own
accumulation logic. Calling `extract_maintainer()`/`extract_downstream()`
directly with a fixed, literal `registry` dict (and, for the maintainer
profile, a fixed `pricing` dict and `plugin_version` string) isolates the
golden to exactly what issue #2041 is chartered to protect.

REGENERATING GOLDENS: an intended behavior change must be a reviewable
`git diff` on the `.golden.json` files, not a hand-edit. Regenerate with:

    python3 tests/scripts/test_session_report_golden.py

then re-run this file under pytest and review the resulting `git diff`.
"""

from __future__ import annotations

import json

from _session_report_golden_fixtures import (
    CORPUS_ROOT,
    EXTRACT_SESSION_REPORT_GOLDEN,
    PLUGIN_VERSION,
    PRICING,
    REGISTRY,
    SENTINELS,
    SESSION_EXTRACT_GOLDEN,
    SESSION_REPORT_SCRIPT,
    load_module,
)


def _session_report_maintainer_digest() -> dict:
    module = load_module(SESSION_REPORT_SCRIPT, "_golden_session_report_maintainer")
    paths = module._all_transcripts_under(CORPUS_ROOT)
    return module.extract_maintainer(
        paths,
        PRICING,
        REGISTRY,
        plugin_version=PLUGIN_VERSION,
        projects_root=CORPUS_ROOT,
    )


def _session_report_downstream_digest() -> dict:
    module = load_module(SESSION_REPORT_SCRIPT, "_golden_session_report_downstream")
    paths = module._all_transcripts(CORPUS_ROOT)
    return module.extract_downstream(paths, REGISTRY, CORPUS_ROOT)


def _dump(digest: dict) -> str:
    return json.dumps(digest, indent=2, sort_keys=True) + "\n"


def test_session_report_maintainer_matches_golden():
    actual = _dump(_session_report_maintainer_digest())
    expected = SESSION_EXTRACT_GOLDEN.read_text(encoding="utf-8")
    assert actual == expected, (
        "session_report.py --profile maintainer's extract_maintainer() "
        "output changed — see module docstring for how to review and "
        "regenerate the golden."
    )


def test_session_report_downstream_matches_golden():
    actual = _dump(_session_report_downstream_digest())
    expected = EXTRACT_SESSION_REPORT_GOLDEN.read_text(encoding="utf-8")
    assert actual == expected, (
        "session_report.py --profile downstream's extract_downstream() "
        "output changed — see module docstring for how to review and "
        "regenerate the golden."
    )


def test_no_sentinel_leaks_in_either_golden():
    for golden in (SESSION_EXTRACT_GOLDEN, EXTRACT_SESSION_REPORT_GOLDEN):
        raw = golden.read_text(encoding="utf-8")
        for sentinel in SENTINELS:
            assert sentinel not in raw, f"{sentinel!r} leaked into {golden.name}"


def test_sync_schemas_accepts_v3():
    module = load_module(SESSION_REPORT_SCRIPT, "_golden_session_report_schemas")
    assert "session-sync/v3" in module.SYNC_SCHEMAS, (
        "session_report.py's exported SYNC_SCHEMAS (the one place a reader "
        "should check an accepted schema, per ADR 0036) does not list its "
        "own current sync schema."
    )


def test_accepts_a_v2_sync_record_deliberately(tmp_path):
    """A v2 sync record (as historically written by the now-retired
    predecessor) must be accepted by session_report.py's reader, not
    silently dropped -- the exact ADR 0036 failure mode this repo's
    schema-versioning discipline guards against."""
    module = load_module(SESSION_REPORT_SCRIPT, "_golden_session_report_v2_record")
    digests_root = tmp_path / "digests"
    host_dir = digests_root / "host-a"
    host_dir.mkdir(parents=True)
    v2_record = {
        "schema": "session-sync/v2",
        "plugin_version": "1.0.0",
        "host": "host-a",
        "project": "proj",
        "session_id": "sid-v2",
        "ts": "2026-01-01T00:00:00Z",
        "sessions": 1,
        "tokens": {"input_tokens": 10, "output_tokens": 5},
        "cost_usd": 0.01,
        "cache_hit_ratio": 0.0,
        "by_model": {},
        "by_thread": {},
        "rework": {},
        "accuracy": {"tool_calls": 0, "tool_error_rate": 0.0, "user_correction_turns": 0},
        "gate": {},
        "utilization": {},
    }
    (host_dir / "session-digest.jsonl").write_text(json.dumps(v2_record) + "\n")
    records = module._read_synced_records(digests_root)
    assert len(records) == 1, (
        "a v2-schema sync record (deliberately still in SYNC_SCHEMAS) was "
        "silently dropped instead of being read"
    )
    assert records[0]["session_id"] == "sid-v2"


def _regenerate() -> None:
    SESSION_EXTRACT_GOLDEN.write_text(
        _dump(_session_report_maintainer_digest()), encoding="utf-8"
    )
    EXTRACT_SESSION_REPORT_GOLDEN.write_text(
        _dump(_session_report_downstream_digest()), encoding="utf-8"
    )
    print(f"wrote {SESSION_EXTRACT_GOLDEN}")
    print(f"wrote {EXTRACT_SESSION_REPORT_GOLDEN}")


if __name__ == "__main__":
    _regenerate()
