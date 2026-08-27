"""Golden-file + schema-versioning coverage for `session_report.py`'s two
profiles (issue #2046, epic #2040).

Sibling of `test_session_report_golden.py` (the harness that already
golden-tests the two predecessor scripts this file's subject replaces), not
an extension of it: `session_report.py` ships under `plugins/dev-team/scripts/`
and is subject to the 3.10 floor (ADR 0031), so this file is one of
`tests/repo/test_python_floor.py`'s `FLOOR_TEST_SLICE` members. Its sibling
is NOT, because `test_session_extract_matches_golden` there imports
`scripts/session_extract.py`, a monorepo-only script that legitimately uses
`datetime.UTC` (3.11+, out of the floor's scope). Keeping this file's
imports free of that module (see `_session_report_golden_fixtures.py`'s own
docstring) is what makes this split matter, not merely tidy.

`session_report.py` --profile maintainer must match `session_extract.py`'s
golden byte-for-byte, MODULO the documented `session-digest/v2` ->
`session-digest/v3` schema-version bump (session_report.py is a new entry
point stamping its own current schema; the still-present predecessor keeps
emitting v2 unchanged). --profile downstream must match
`extract_session_report.py`'s golden with NO exception at all: that
predecessor's `extract()` never emits a `schema` field (only its `main()`'s
report wrapper does, which this golden harness deliberately never calls —
see `test_session_report_golden.py`'s module docstring, INVOCATION).
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


def test_session_report_maintainer_matches_patched_golden():
    expected = SESSION_EXTRACT_GOLDEN.read_text(encoding="utf-8").replace(
        '"schema": "session-digest/v2"', '"schema": "session-digest/v3"'
    )
    actual = _dump(_session_report_maintainer_digest())
    assert actual == expected, (
        "session_report.py --profile maintainer's extract_maintainer() output "
        "diverged from scripts/session_extract.py's golden by more than the "
        "documented schema-version bump."
    )


def test_session_report_downstream_matches_golden():
    actual = _dump(_session_report_downstream_digest())
    expected = EXTRACT_SESSION_REPORT_GOLDEN.read_text(encoding="utf-8")
    assert actual == expected, (
        "session_report.py --profile downstream's extract_downstream() output "
        "diverged from plugins/dev-team/scripts/extract_session_report.py's "
        "golden -- extract() never emits a schema field, so no bump is "
        "expected here at all."
    )


def test_no_sentinel_leaks_in_session_report_output():
    for raw in (
        json.dumps(_session_report_maintainer_digest()),
        json.dumps(_session_report_downstream_digest()),
    ):
        for sentinel in SENTINELS:
            assert sentinel not in raw, f"{sentinel!r} leaked into session_report.py output"


def test_session_report_sync_schemas_accepts_v3():
    module = load_module(SESSION_REPORT_SCRIPT, "_golden_session_report_schemas")
    assert "session-sync/v3" in module.SYNC_SCHEMAS, (
        "session_report.py's exported SYNC_SCHEMAS (the one place a reader "
        "should check an accepted schema, per ADR 0036) does not list its "
        "own current sync schema."
    )


def test_session_report_accepts_a_v2_sync_record_deliberately(tmp_path):
    """A v2 sync record (written by the still-present predecessor,
    scripts/session_extract.py) must be accepted by session_report.py's
    reader, not silently dropped -- the exact ADR 0036 failure mode this
    slice's schema-versioning acceptance criterion guards against."""
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
