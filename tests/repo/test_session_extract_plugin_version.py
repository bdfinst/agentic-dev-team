"""#1471: session_report.py tags digest/sync/trend records with
plugin_version (read from .claude-plugin/plugin.json), so stale
recommendations from an older plugin version can be told apart from current
ones. #1480: --rollup/--escalate/--correlate can be scoped to the current +
immediately previous observed plugin_version via --version-scope.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "session_report.py"
FIX = REPO_ROOT / "tests" / "fixtures" / "session-review" / "sample-transcript.jsonl"


def _fake_plugin_root(tmp_path: Path, version: str) -> Path:
    root = tmp_path / "fake-plugin"
    manifest_dir = root / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(json.dumps({"version": version}))
    return root


def _run(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXTRACT), "--profile", "maintainer", *extra],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# #1471: digest / sync / trend tagging
# ---------------------------------------------------------------------------


def test_extract_tags_digest_with_plugin_version_from_manifest(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "9.1.2")
    result = _run(
        "--transcript", str(FIX), "--plugin-root", str(plugin_root)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    digest = json.loads(result.stdout)
    assert digest["plugin_version"] == "9.1.2"


def test_extract_falls_back_to_unknown_when_manifest_missing(
    tmp_path: Path,
) -> None:
    empty_root = tmp_path / "no-manifest"
    empty_root.mkdir()
    result = _run(
        "--transcript", str(FIX), "--plugin-root", str(empty_root)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    digest = json.loads(result.stdout)
    assert digest["plugin_version"] == "unknown"


def test_trend_append_record_carries_plugin_version(tmp_path: Path) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "3.0.0")
    log = tmp_path / "session-digest.jsonl"
    result = _run(
        "--transcript",
        str(FIX),
        "--plugin-root",
        str(plugin_root),
        "--append",
        str(log),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(log.read_text().splitlines()[0])
    assert record["plugin_version"] == "3.0.0"


def test_sync_record_carries_plugin_version(tmp_path: Path) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "4.5.6")
    projects = tmp_path / "projects" / "projA"
    projects.mkdir(parents=True)
    (projects / "sess-a.jsonl").write_text(
        '{"type":"assistant","cwd":"/home/u/work/alpha","sessionId":"s-a",'
        '"timestamp":"2026-06-07T10:00:00Z",'
        '"message":{"model":"claude-opus-4-8","usage":{"input_tokens":10,'
        '"output_tokens":1}}}\n'
    )
    out = tmp_path / "digests" / "testhost" / "session-digest.jsonl"
    watermark = tmp_path / "watermark.json"
    result = _run(
        "--sync-out",
        str(out),
        "--watermark",
        str(watermark),
        "--projects-root",
        str(tmp_path / "projects"),
        "--host",
        "testhost",
        "--plugin-root",
        str(plugin_root),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(out.read_text().splitlines()[0])
    assert record["plugin_version"] == "4.5.6"


# ---------------------------------------------------------------------------
# #1480: --version-scope current-and-previous
# ---------------------------------------------------------------------------


def _seed_versioned_digests(tmp_path: Path) -> Path:
    box = tmp_path / "digests" / "box"
    box.mkdir(parents=True)
    (box / "session-digest.jsonl").write_text(
        "\n".join(
            json.dumps(rec)
            for rec in (
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "10.23.0",
                    "host": "box",
                    "project": "p",
                    "session_id": "s-current",
                    "tokens": {"input_tokens": 100},
                    "cost_usd": 1.0,
                    "rework": {"failed_edits": 1},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0.0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "10.22.0",
                    "host": "box",
                    "project": "p",
                    "session_id": "s-previous",
                    "tokens": {"input_tokens": 200},
                    "cost_usd": 2.0,
                    "rework": {"failed_edits": 1},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0.0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "9.0.0",
                    "host": "box",
                    "project": "p",
                    "session_id": "s-stale",
                    "tokens": {"input_tokens": 400},
                    "cost_usd": 4.0,
                    "rework": {"failed_edits": 1},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0.0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
                {
                    # legacy pre-#1471 record with no plugin_version at all.
                    "schema": "session-sync/v1",
                    "host": "box",
                    "project": "p",
                    "session_id": "s-untagged",
                    "tokens": {"input_tokens": 800},
                    "cost_usd": 8.0,
                    "rework": {"failed_edits": 1},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0.0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
            )
        )
        + "\n"
    )
    return tmp_path / "digests"


def test_rollup_defaults_to_all_versions_unscoped(tmp_path: Path) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = _seed_versioned_digests(tmp_path)
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    # unscoped by default -> all four sessions, including the untagged legacy one
    assert data["sessions"] == 4
    assert data["version_window"] == []


def test_rollup_current_and_previous_excludes_stale_and_untagged(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = _seed_versioned_digests(tmp_path)
    result = _run(
        "--rollup",
        str(digests),
        "--plugin-root",
        str(plugin_root),
        "--version-scope",
        "current-and-previous",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    # only s-current (10.23.0) and s-previous (10.22.0) survive; the 9.0.0
    # and untagged-legacy sessions are excluded.
    assert data["sessions"] == 2
    assert sorted(data["version_window"]) == ["10.22.0", "10.23.0"]
    assert data["tokens"]["input_tokens"] == 300


def test_escalate_carries_version_window_through(tmp_path: Path) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = _seed_versioned_digests(tmp_path)
    result = _run(
        "--escalate",
        str(digests),
        "--plugin-root",
        str(plugin_root),
        "--version-scope",
        "current-and-previous",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["sessions"] == 2
    assert sorted(data["version_window"]) == ["10.22.0", "10.23.0"]


def test_correlate_respects_version_scope(tmp_path: Path) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests" / "box"
    digests.mkdir(parents=True)
    digests.joinpath("session-digest.jsonl").write_text(
        "\n".join(
            json.dumps(rec)
            for rec in (
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "10.23.0",
                    "session_id": "s1",
                    "gate": {"commit_attempts": 1, "commit_bypasses": 0},
                    "rework": {"failed_edits": 0},
                },
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "10.22.0",
                    "session_id": "s2",
                    "gate": {"commit_attempts": 1, "commit_bypasses": 1},
                    "rework": {"failed_edits": 1},
                },
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "9.0.0",
                    "session_id": "s3",
                    "gate": {"commit_attempts": 1, "commit_bypasses": 1},
                    "rework": {"failed_edits": 99},
                },
            )
        )
        + "\n"
    )
    result = _run(
        "--correlate",
        str(tmp_path / "digests"),
        "--plugin-root",
        str(plugin_root),
        "--version-scope",
        "current-and-previous",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    # s3 (9.0.0, outside the current+previous window) is excluded -> only
    # s1 (clean) and s2 (bypass) counted; its rework of 99 must not leak in.
    assert data["committing_sessions"] == 2
    assert data["bypass_sessions"] == 1
    assert data["clean_sessions"] == 1
    assert data["mean_rework_when_bypassed"] == 1


def test_version_window_falls_back_to_latest_observed_when_current_absent(
    tmp_path: Path,
) -> None:
    """If the running plugin's own version has no matching telemetry yet
    (e.g. just bumped), fall back to the two most recent versions actually
    observed rather than yielding an empty window."""
    plugin_root = _fake_plugin_root(tmp_path, "99.0.0")
    digests = _seed_versioned_digests(tmp_path)
    result = _run(
        "--rollup",
        str(digests),
        "--plugin-root",
        str(plugin_root),
        "--version-scope",
        "current-and-previous",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    # current (99.0.0) has no telemetry -> falls back to the newest OBSERVED
    # version that is older than current (10.23.0).
    assert sorted(data["version_window"]) == ["10.23.0", "99.0.0"]
    assert data["sessions"] == 1


def test_version_window_never_picks_a_version_newer_than_current(
    tmp_path: Path,
) -> None:
    """A peer host running a newer plugin version than this machine must
    never be treated as "the previous version" — only versions strictly
    OLDER than `current` are eligible."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    box = tmp_path / "digests" / "box"
    box.mkdir(parents=True)
    box.joinpath("session-digest.jsonl").write_text(
        "\n".join(
            json.dumps(rec)
            for rec in (
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "10.22.0",
                    "session_id": "s-older",
                    "tokens": {"input_tokens": 1},
                    "cost_usd": 0,
                    "rework": {},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
                {
                    # a host running a NEWER version than this machine's
                    # current (11.0.0 > 10.23.0) must never be picked as
                    # "previous".
                    "schema": "session-sync/v1",
                    "plugin_version": "11.0.0",
                    "session_id": "s-newer",
                    "tokens": {"input_tokens": 1},
                    "cost_usd": 0,
                    "rework": {},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
            )
        )
        + "\n"
    )
    result = _run(
        "--rollup",
        str(tmp_path / "digests"),
        "--plugin-root",
        str(plugin_root),
        "--version-scope",
        "current-and-previous",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert sorted(data["version_window"]) == ["10.22.0", "10.23.0"]
    assert data["sessions"] == 1  # only s-older is in scope


def test_version_window_is_empty_when_current_version_is_unknown(
    tmp_path: Path,
) -> None:
    """If this machine's own plugin.json can't be read, the current version
    is "unknown" — the window must fail CLOSED (empty), never silently widen
    to admit every peer record (including ones also tagged "unknown")."""
    empty_root = tmp_path / "no-manifest"
    empty_root.mkdir()
    digests = _seed_versioned_digests(tmp_path)
    result = _run(
        "--rollup",
        str(digests),
        "--plugin-root",
        str(empty_root),
        "--version-scope",
        "current-and-previous",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["version_window"] == []
    assert data["sessions"] == 0


def test_correlate_default_all_scope_carries_empty_version_window(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests" / "box"
    digests.mkdir(parents=True)
    digests.joinpath("session-digest.jsonl").write_text(
        json.dumps(
            {
                "schema": "session-sync/v1",
                "plugin_version": "10.23.0",
                "session_id": "s1",
                "gate": {"commit_attempts": 1, "commit_bypasses": 0},
                "rework": {},
            }
        )
        + "\n"
    )
    result = _run(
        "--correlate",
        str(tmp_path / "digests"),
        "--plugin-root",
        str(plugin_root),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    # --correlate now carries version_window like its --rollup/--escalate
    # siblings, even when unscoped (default "all").
    assert data["version_window"] == []
    assert data["committing_sessions"] == 1


def test_load_plugin_version_falls_back_to_unknown_on_malformed_json(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bad-plugin"
    manifest_dir = root / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text("{not valid json")
    result = _run("--transcript", str(FIX), "--plugin-root", str(root))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["plugin_version"] == "unknown"


def test_load_plugin_version_falls_back_to_unknown_on_empty_string(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "")
    result = _run("--transcript", str(FIX), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["plugin_version"] == "unknown"


def test_load_plugin_version_rejects_oversized_or_malformed_version_string(
    tmp_path: Path,
) -> None:
    """Security hardening (#1480 review): a version string that isn't a short
    semver-ish token must never be reflected verbatim into a persisted
    stream — it collapses to "unknown", same as a missing/malformed manifest."""
    plugin_root = _fake_plugin_root(tmp_path, "x" * 500)
    result = _run("--transcript", str(FIX), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["plugin_version"] == "unknown"


def test_rollup_survives_a_peer_record_with_a_hostile_plugin_version(
    tmp_path: Path,
) -> None:
    """A peer host's synced digest is a different trust domain (#1480 review)
    — a record with a pathologically long digit-only plugin_version must not
    crash --rollup (previously an uncaught ValueError from int() on a
    >4300-digit string), and one with a non-string plugin_version must not
    crash it either (previously an uncaught TypeError from set membership).
    Both normalize to "no version" and are simply excluded from scope."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    box = tmp_path / "digests" / "box"
    box.mkdir(parents=True)
    box.joinpath("session-digest.jsonl").write_text(
        "\n".join(
            json.dumps(rec)
            for rec in (
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "1" * 5000,
                    "session_id": "s-huge-digits",
                    "tokens": {"input_tokens": 1},
                    "cost_usd": 0,
                    "rework": {},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
                {
                    "schema": "session-sync/v1",
                    "plugin_version": ["not", "a", "string"],
                    "session_id": "s-non-string",
                    "tokens": {"input_tokens": 1},
                    "cost_usd": 0,
                    "rework": {},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
                {
                    "schema": "session-sync/v1",
                    "plugin_version": "10.23.0",
                    "session_id": "s-legit",
                    "tokens": {"input_tokens": 1},
                    "cost_usd": 0,
                    "rework": {},
                    "accuracy": {
                        "tool_calls": 1,
                        "tool_error_rate": 0,
                        "user_correction_turns": 0,
                    },
                    "utilization": {"skills_invoked": {}, "agents_invoked": {}},
                },
            )
        )
        + "\n"
    )
    result = _run(
        "--rollup",
        str(tmp_path / "digests"),
        "--plugin-root",
        str(plugin_root),
        "--version-scope",
        "current-and-previous",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    # the two hostile records are normalized to "no version" and excluded;
    # only the legitimately-tagged session survives the scope.
    assert data["sessions"] == 1


# ---------------------------------------------------------------------------
# #2016: peer-written host/project/name keys are normalized at ingestion
# ---------------------------------------------------------------------------


def _base_sync_record(host: str, project: str, session_id: str) -> dict:
    return {
        "schema": "session-sync/v1",
        "host": host,
        "project": project,
        "session_id": session_id,
        "tokens": {"input_tokens": 1},
        "cost_usd": 0,
        "rework": {},
        "accuracy": {
            "tool_calls": 1,
            "tool_error_rate": 0,
            "user_correction_turns": 0,
            "by_skill": {},
            "by_agent": {},
        },
        "utilization": {
            "skills_invoked": {},
            "agents_invoked": {},
            "agent_dispatches": {},
        },
    }


def _write_digest(digests_root: Path, host: str, records: list[dict]) -> None:
    box = digests_root / host
    box.mkdir(parents=True)
    (box / "session-digest.jsonl").write_text(
        "\n".join(json.dumps(rec) for rec in records) + "\n"
    )


def test_rollup_sanitizes_hostile_project_path_to_safe_name_sentinel(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record(
        "hostile-host", "/Users/alice/secret-client-work", "s-hostile"
    )
    _write_digest(digests, "hostile-host", [hostile])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["projects"] == ["other"]
    assert "/Users/alice/secret-client-work" not in data["projects"]


@pytest.mark.parametrize(
    "field",
    [
        "utilization.skills_invoked",
        "utilization.agents_invoked",
        "utilization.agent_dispatches",
        "accuracy.by_skill",
        "accuracy.by_agent",
    ],
)
def test_rollup_sanitizes_unsafe_keys_in_each_name_bearing_dict(
    tmp_path: Path, field: str
) -> None:
    """An unsafe key (one `_safe_name` would reject) in any of the five
    name-bearing dicts `rollup()` reads must not crash ingestion, and a
    well-formed sibling record from a different host must still survive in
    the output — proving the normalization is wired at each of the five
    field paths independently, not inferred from one exemplar."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"

    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    top, sub = field.split(".")
    hostile[top][sub] = {"../../etc/passwd": 5}
    _write_digest(digests, "hostile-host", [hostile])

    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["utilization"]["skills_invoked"] = {"plan": 1}
    _write_digest(digests, "good-host", [well_formed])

    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["sessions"] == 2
    assert "good-host" in data["hosts"]
    assert data["utilization"]["skills_invoked"]["plan"] == 1
    # the hostile key sanitizes to the _UNSAFE_NAME sentinel ("other") in
    # the SAME field it was written to, proving the normalization is wired
    # at this specific field path rather than inferred from one exemplar.
    assert data[top][sub].get("other") == 5


def test_rollup_survives_a_peer_record_with_an_unhashable_host(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"

    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["host"] = ["not", "a", "string"]
    _write_digest(digests, "hostile-host", [hostile])

    well_formed = _base_sync_record("good-host", "p", "s-good")
    _write_digest(digests, "good-host", [well_formed])

    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["sessions"] == 2
    assert "good-host" in data["hosts"]
    # the unhashable host actually normalized to the sentinel, not just
    # "didn't crash" — it must be present as its own bucket, not silently
    # dropped or merged into the well-formed host.
    assert "other" in data["hosts"]


def test_rollup_well_formed_record_round_trips_host_project_cost_unchanged(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    record = _base_sync_record("testhost", "myproject", "s1")
    record["cost_usd"] = 1.5
    _write_digest(digests, "testhost", [record])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["hosts"] == ["testhost"]
    assert data["projects"] == ["myproject"]
    assert data["cost_usd"] == 1.5


def test_rewrite_name_keys_buckets_non_string_keys_and_merges_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`json.loads` always yields string dict keys (JSON object keys are
    syntactically strings), so a truly non-string key can never arrive via a
    peer's session-digest.jsonl file — but `_rewrite_name_keys` is a general
    helper, so it must not raise `AttributeError` if one ever reaches it
    (e.g. via a future non-JSON caller), and a normalization collision (two
    keys landing in the same bucket) must MERGE by summing, never drop a
    peer-attributed count."""
    monkeypatch.syspath_prepend(str(REPO_ROOT / "plugins" / "dev-team" / "scripts"))
    import session_report

    # 123 (non-string) and "!!!" (fails _safe_name's charset) both collapse
    # into the _UNSAFE_NAME bucket ("other") and their values must sum.
    result = session_report._rewrite_name_keys({123: 2, "plan": 3, "!!!": 4})
    assert result == {"plan": 3, "other": 6}


def test_rewrite_name_keys_guards_non_numeric_peer_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2016 finding 1: a peer-supplied VALUE in a name-bearing dict is as
    untrusted as its key — summing it unguarded (`out[key] = out.get(key, 0)
    + v`) raises an uncaught TypeError the moment it's a string/None/list/
    dict, aborting the caller for every host. Each non-numeric value must
    coerce through `_safe_number` to 0 instead, and a legitimate numeric
    value must still pass through unaffected."""
    monkeypatch.syspath_prepend(str(REPO_ROOT / "plugins" / "dev-team" / "scripts"))
    import session_report

    result = session_report._rewrite_name_keys(
        {
            "plan": 3,
            "bad-str": "nope",
            "bad-null": None,
            "bad-list": [1, 2],
            "bad-dict": {},
        }
    )
    assert result == {
        "plan": 3,
        "bad-str": 0,
        "bad-null": 0,
        "bad-list": 0,
        "bad-dict": 0,
    }


# ---------------------------------------------------------------------------
# #2016 (Step 1.2): peer-supplied numeric fields and container shapes are
# guarded at ingestion
# ---------------------------------------------------------------------------


def test_rollup_boolean_cost_usd_treated_as_zero_not_one(tmp_path: Path) -> None:
    """`bool` is an `int` subclass in Python -- a hostile `cost_usd: true`
    must coerce to 0, never silently promote to 1.0."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["cost_usd"] = True
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["cost_usd"] = 2.0
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["cost_usd"] == 2.0


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
def test_rollup_non_finite_cost_usd_treated_as_zero_and_does_not_poison_siblings(
    tmp_path: Path, bad_value: float
) -> None:
    """A non-finite `cost_usd` (NaN/Infinity) must not just avoid crashing --
    if it leaked through unguarded, `cost += nan` (or `+= inf`) would poison
    the running total for EVERY other host's aggregate cost in the same run,
    not just the hostile record's own contribution."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["cost_usd"] = bad_value
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["cost_usd"] = 3.0
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["cost_usd"] == 3.0
    assert "good-host" in data["hosts"]


def test_rollup_oversized_integer_cost_usd_treated_as_zero_without_overflow(
    tmp_path: Path,
) -> None:
    """A 350+ digit integer `cost_usd` is legal JSON (no wire-size limit) but
    exceeds `sys.float_info.max` -- casting it through `float()` to check
    finiteness raises `OverflowError` and aborts the run for every host.
    Must coerce to 0 without raising, and the well-formed sibling's cost
    must survive unpoisoned."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["cost_usd"] = int("1" * 350)
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["cost_usd"] = 4.0
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["cost_usd"] == 4.0
    assert "good-host" in data["hosts"]


def test_rollup_cost_usd_above_2_53_treated_as_zero(tmp_path: Path) -> None:
    """#2016 finding 3: `_safe_number`'s magnitude bound tightened from
    `sys.float_info.max` to `2**53` (the exact-integer double-precision
    range) -- a value in the NEWLY-rejected band (well above `2**53` ~=
    9.007e15, but far below the old `sys.float_info.max` bound) previously
    passed `_safe_number` unchanged and overflowed a downstream multiply
    (`round(c * 1e6)` for `cost_micro`) to `inf`, raising an uncaught
    OverflowError from `round(inf)`. Must coerce to 0 without raising, and
    the well-formed sibling's cost must survive unpoisoned."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["cost_usd"] = 10**16  # > 2**53, far under sys.float_info.max
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["cost_usd"] = 5.0
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["cost_usd"] == 5.0
    assert "good-host" in data["hosts"]


def test_rollup_survives_a_non_numeric_string_inside_rework(tmp_path: Path) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["rework"] = {"failed_edits": "not-a-number"}
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["rework"] = {"failed_edits": 2}
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["rework"]["failed_edits"] == 2


def test_rollup_excludes_unknown_rework_keys_from_output(tmp_path: Path) -> None:
    """#2016 finding 2: `rework` must be restricted to the known
    `_REWORK_KEYS` schema, not merely value-coerced -- an unknown/hostile
    key is the same key-leak class the `project`/`host` sanitization closes,
    and it was previously emitted verbatim into the shared rollup output.
    `_session_rework()` reads only `_REWORK_KEYS`, so excluding the rest
    drops nothing legitimate."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["rework"] = {"failed_edits": 1, "/etc/passwd": 99}
    _write_digest(digests, "hostile-host", [hostile])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["rework"]["failed_edits"] == 1
    assert "/etc/passwd" not in data["rework"]


def test_rollup_non_dict_utilization_does_not_crash_and_contributes_nothing(
    tmp_path: Path,
) -> None:
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["utilization"] = "not-a-dict"
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["utilization"]["skills_invoked"] = {"plan": 1}
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["sessions"] == 2
    assert data["utilization"]["skills_invoked"] == {"plan": 1}


def test_rollup_survives_a_digest_line_that_decodes_to_a_non_dict(
    tmp_path: Path,
) -> None:
    """#2016 round-4 closing-pass finding: `_iter_records` only excludes
    UNDECODABLE lines -- a line that decodes to a bare JSON array, string,
    number, or null is yielded as-is, and `_read_synced_records()`'s
    `rec.get("schema")` raised an uncaught AttributeError on it, aborting
    --rollup for every host over one malformed line in any peer's digest
    file. Must skip non-dict decoded values instead, and the well-formed
    sibling record (written after the bad lines in the same file) must
    still be counted."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    well_formed = _base_sync_record("good-host", "p", "s-good")
    box = digests / "good-host"
    box.mkdir(parents=True)
    (box / "session-digest.jsonl").write_text(
        "\n".join(["[]", '"x"', "5", "null", "true", json.dumps(well_formed)]) + "\n"
    )
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["sessions"] == 1
    assert data["hosts"] == ["good-host"]


@pytest.mark.parametrize("bad_value", ["not-a-dict", [1, 2]])
def test_rollup_survives_a_non_dict_inner_utilization_field(
    tmp_path: Path, bad_value: object
) -> None:
    """#2016 closing-pass finding 1: `_normalize_name_dicts` only rewrote a
    field `if isinstance(value, dict)`, leaving a non-dict INNER field (e.g.
    `utilization.skills_invoked` set to a string or list by a hostile peer)
    untouched -- distinct from `test_rollup_non_dict_utilization_does_not_
    crash_and_contributes_nothing` above, which only covers the OUTER
    `utilization` container being non-dict. `rollup()` then calls `.items()`
    on the untouched inner field unguarded (`(u.get("skills_invoked", {}) or
    {}).items()`) -- a truthy non-dict value isn't rescued by `or {}`, so
    `.items()` raised an uncaught AttributeError and aborted --rollup for
    every host. Must coerce to {} instead, and the well-formed sibling's
    data must still appear."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["utilization"]["skills_invoked"] = bad_value
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["utilization"]["skills_invoked"] = {"plan": 1}
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["sessions"] == 2
    assert data["utilization"]["skills_invoked"] == {"plan": 1}


# ---------------------------------------------------------------------------
# #2079: _safe_number bounded magnitude but not sign
# ---------------------------------------------------------------------------


def test_safe_number_clamps_negative_values_directly(monkeypatch) -> None:
    """Unit-level pin on `_safe_number` itself, alongside the existing
    magnitude/finiteness cases the end-to-end tests below cover: a negative
    value is exactly as untrusted as a non-numeric one and must clamp to 0,
    the same way NaN/Infinity/oversized-magnitude already do."""
    monkeypatch.syspath_prepend(str(REPO_ROOT / "plugins" / "dev-team" / "scripts"))
    import session_report

    assert session_report._safe_number(-999) == 0
    assert session_report._safe_number(-0.5) == 0
    assert session_report._safe_number(-(2**53) - 1) == 0  # negative AND oversized
    assert session_report._safe_number(0) == 0
    assert session_report._safe_number(5) == 5
    assert session_report._safe_number(3.5) == 3.5


def test_rollup_negative_cost_usd_clamped_to_zero_not_subtracted(
    tmp_path: Path,
) -> None:
    """#2079 finding 2/3: an unclamped negative `cost_usd` would subtract
    from the cross-host total (and could drag cost_meter.py's CI regression
    baseline mean to <= 0, silently disabling that gate). Must clamp to 0,
    leaving the well-formed sibling's cost the whole rolled-up total."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["cost_usd"] = -500.0
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["cost_usd"] = 6.0
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["cost_usd"] == 6.0
    assert "good-host" in data["hosts"]


def test_rollup_negative_skill_count_does_not_corrupt_cross_host_sum(
    tmp_path: Path,
) -> None:
    """#2079 finding 1: an unclamped hostile `{"code-review": -999}` would
    drive the CROSS-HOST Counter negative -- combined with the `c > 0` gate
    `rollup()` uses for never_observed_skills/never_observed_agents, that
    silently evicts a skill OTHER hosts genuinely invoked from
    `invoked_skills`. The genuinely-invoked count must survive intact."""
    plugin_root = _fake_plugin_root(tmp_path, "10.23.0")
    digests = tmp_path / "digests"
    hostile = _base_sync_record("hostile-host", "p", "s-hostile")
    hostile["utilization"]["skills_invoked"] = {"code-review": -999}
    _write_digest(digests, "hostile-host", [hostile])
    well_formed = _base_sync_record("good-host", "p", "s-good")
    well_formed["utilization"]["skills_invoked"] = {"code-review": 3}
    _write_digest(digests, "good-host", [well_formed])
    result = _run("--rollup", str(digests), "--plugin-root", str(plugin_root))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["utilization"]["skills_invoked"] == {"code-review": 3}
