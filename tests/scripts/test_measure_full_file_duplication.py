"""Unit tests for scripts/measure_full_file_duplication.py (#1618, the
measurement follow-up to #1611).

Covers the pure functions (Context-needs parsing, token estimation, round
clustering, timestamp parsing, subagent-type shortening, the avoidable-token
formula, the percentile-distribution helper) plus the two I/O boundaries
(`theoretical_full_file_agents` against a synthetic agents-dir + registry,
and `collect_agent_dispatches` against a synthetic transcript in both the
newer sibling-subagent-file layout and the older inline-isSidechain layout)
and the `_round_report_row` aggregation `cmd_report` builds on — so a
regression in any of the fix-round corrections (per-instance vs per-type
counting, timestamp-string vs parsed-instant sorting, the attributionAgent
fallback, the file-missing signal) is caught without needing a real
historical transcript in CI.
"""

from __future__ import annotations

import importlib.util
import json

from _repo_root import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "measure_full_file_duplication.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_full_file_duplication", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mfd = _load()


# ---------------------------------------------------------------------------
# parse_context_needs_tokens
# ---------------------------------------------------------------------------


class TestParseContextNeedsTokens:
    def test_single_value(self):
        assert mfd.parse_context_needs_tokens("Context needs: full-file\n") == {
            "full-file"
        }

    def test_combined_value(self):
        text = "Context needs: artifact-stream, diff-only\n"
        assert mfd.parse_context_needs_tokens(text) == {"artifact-stream", "diff-only"}

    def test_parenthetical_aside_is_stripped(self):
        text = "Context needs: full-file (reads plan + git state)\n"
        assert mfd.parse_context_needs_tokens(text) == {"full-file"}

    def test_missing_declaration_is_empty_set(self):
        assert mfd.parse_context_needs_tokens("No such field here.\n") == set()

    def test_case_insensitive(self):
        assert mfd.parse_context_needs_tokens("Context needs: FULL-FILE\n") == {
            "full-file"
        }

    def test_anchored_not_bare_substring(self):
        # A prose line merely mentioning "Context needs" mid-sentence must
        # NOT match — only a line whose Context needs: declaration starts
        # (after whitespace) at column 0 does. Regression guard for an
        # earlier version that used `stripped.lower().startswith(...)`
        # after only a `.strip()`, which a leading-whitespace variant would
        # still have matched, but a genuine prose mention would not — this
        # pins the anchor specifically against a prose sentence.
        text = "See the Context needs: section below for details.\n"
        assert mfd.parse_context_needs_tokens(text) == set()


# ---------------------------------------------------------------------------
# estimate_tokens / avoidable_tokens_estimate
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_scales_with_byte_count(self):
        assert mfd.estimate_tokens(4000) == 4000 // mfd.BYTES_PER_TOKEN_ESTIMATE

    def test_floors_at_one_for_tiny_files(self):
        assert mfd.estimate_tokens(1) == 1
        assert mfd.estimate_tokens(0) == 1


class TestAvoidableTokensEstimate:
    def test_zero_or_one_agent_is_never_avoidable(self):
        assert mfd.avoidable_tokens_estimate(1000, 0) == 0
        assert mfd.avoidable_tokens_estimate(1000, 1) == 0

    def test_n_agents_charges_n_minus_one_duplicate_reads(self):
        assert mfd.avoidable_tokens_estimate(1000, 4) == 3000


# ---------------------------------------------------------------------------
# _parse_iso / cluster_rounds
# ---------------------------------------------------------------------------


class TestParseIso:
    def test_z_suffix_normalized(self):
        t1 = mfd._parse_iso("2026-08-01T19:00:00.000Z")
        t2 = mfd._parse_iso("2026-08-01T19:00:00.000+00:00")
        assert t1 == t2

    def test_one_second_apart(self):
        t1 = mfd._parse_iso("2026-08-01T19:00:00.000Z")
        t2 = mfd._parse_iso("2026-08-01T19:00:01.000Z")
        assert t2 - t1 == 1.0


def _d(agent_type: str, ts: str, spend: int = 100) -> dict:
    return {"agent_type": agent_type, "timestamp": ts, "input_spend": spend}


class TestClusterRounds:
    def test_dispatches_within_gap_form_one_round(self):
        dispatches = [
            _d("a", "2026-08-01T19:00:00.000Z"),
            _d("b", "2026-08-01T19:00:05.000Z"),
            _d("c", "2026-08-01T19:00:10.000Z"),
        ]
        rounds = mfd.cluster_rounds(dispatches, gap_seconds=90)
        assert len(rounds) == 1
        assert len(rounds[0]) == 3

    def test_dispatches_beyond_gap_split_into_separate_rounds(self):
        dispatches = [
            _d("a", "2026-08-01T19:00:00.000Z"),
            _d("b", "2026-08-01T19:00:05.000Z"),
            _d("c", "2026-08-01T19:05:00.000Z"),  # 295s later, beyond a 90s gap
        ]
        rounds = mfd.cluster_rounds(dispatches, gap_seconds=90)
        assert len(rounds) == 2
        assert len(rounds[0]) == 2
        assert len(rounds[1]) == 1

    def test_empty_input_yields_no_rounds(self):
        assert mfd.cluster_rounds([], gap_seconds=90) == []

    def test_gap_boundary_is_exclusive_not_inclusive(self):
        # Exactly at the gap threshold: still the same round (> gap_seconds
        # is what splits, not >=) — verified by hand: cluster_rounds's own
        # condition is `(t - prev_t) > gap_seconds`.
        dispatches = [
            _d("a", "2026-08-01T19:00:00.000Z"),
            _d("b", "2026-08-01T19:01:30.000Z"),  # exactly 90s later
        ]
        rounds = mfd.cluster_rounds(dispatches, gap_seconds=90)
        assert len(rounds) == 1


class TestRoundSummary:
    def test_full_expected_object(self):
        dispatches = [
            _d("a", "2026-08-01T19:00:00.000Z", spend=100),
            _d("b", "2026-08-01T19:00:05.000Z", spend=250),
        ]
        summary = mfd.round_summary(dispatches)
        assert summary == {
            "n_agents": 2,
            "agent_types": ["a", "b"],
            "start": "2026-08-01T19:00:00.000Z",
            "end": "2026-08-01T19:00:05.000Z",
            "round_total_input_tokens": 350,
        }


# ---------------------------------------------------------------------------
# _short_name / _percentile_distribution
# ---------------------------------------------------------------------------


class TestShortName:
    def test_strips_plugin_qualifier(self):
        assert mfd._short_name("dev-team:correctness-review") == "correctness-review"

    def test_passes_through_unqualified_name(self):
        assert mfd._short_name("correctness-review") == "correctness-review"


class TestPercentileDistribution:
    def test_empty_is_none(self):
        assert mfd._percentile_distribution([]) is None

    def test_odd_count_median_is_middle_value(self):
        dist = mfd._percentile_distribution([1.0, 5.0, 3.0])
        assert dist == {
            "min_pct": 1.0,
            "median_pct": 3.0,
            "max_pct": 5.0,
            "n_rounds_sampled": 3,
        }

    def test_even_count_median_is_average_of_middle_two(self):
        dist = mfd._percentile_distribution([1.0, 2.0, 3.0, 4.0])
        assert dist["median_pct"] == 2.5


# ---------------------------------------------------------------------------
# theoretical_full_file_agents (synthetic agents-dir + registry)
# ---------------------------------------------------------------------------

_REGISTRY_TEXT = """\
## Review Agents

| Name | File | Purpose |
| --- | --- | --- |
| full-file-agent | `agents/full-file-agent.md` | reads whole files |
| diff-only-agent | `agents/diff-only-agent.md` | reads only the diff |
| scoped-out-agent | `agents/scoped-out-agent.md` | never matches .md |
"""

_FULL_FILE_AGENT = """\
---
name: full-file-agent
model: sonnet
---

Scope: always
Context needs: full-file
"""

_DIFF_ONLY_AGENT = """\
---
name: diff-only-agent
model: sonnet
---

Scope: always
Context needs: diff-only
"""

_SCOPED_OUT_AGENT = """\
---
name: scoped-out-agent
model: sonnet
---

Scope:
- **/*.py
Context needs: full-file
"""


def _write_fixture_roster(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "full-file-agent.md").write_text(_FULL_FILE_AGENT, encoding="utf-8")
    (agents_dir / "diff-only-agent.md").write_text(_DIFF_ONLY_AGENT, encoding="utf-8")
    (agents_dir / "scoped-out-agent.md").write_text(_SCOPED_OUT_AGENT, encoding="utf-8")
    registry_path = tmp_path / "agent-registry.md"
    registry_path.write_text(_REGISTRY_TEXT, encoding="utf-8")
    return agents_dir, registry_path


def _minimal_roster(tmp_path):
    """A throwaway single-agent roster — used by tests that don't care about
    the roster's own content (e.g. exercising a target file's own stat()
    failure), so they don't build the full 3-agent fixture only to discard
    most of it (a test-smell-review finding on an earlier version)."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "full-file-agent.md").write_text(_FULL_FILE_AGENT, encoding="utf-8")
    registry_path = tmp_path / "agent-registry.md"
    registry_path.write_text(
        "## Review Agents\n\n| Name | File |\n| --- | --- |\n"
        "| full-file-agent | `agents/full-file-agent.md` |\n",
        encoding="utf-8",
    )
    return agents_dir, registry_path


class TestTheoreticalFullFileAgents:
    def test_only_full_file_and_in_scope_agents_are_returned(self, tmp_path):
        agents_dir, registry_path = _write_fixture_roster(tmp_path)
        roster, warnings = mfd.select_lenses.build_review_roster(agents_dir, registry_path)
        assert warnings == []
        target = tmp_path / "some_doc.md"
        target.write_text("x" * 400, encoding="utf-8")

        agents, file_tokens, lens_warnings, file_missing = mfd.theoretical_full_file_agents(
            target, roster, agents_dir
        )

        # diff-only-agent is excluded (Context needs != full-file);
        # scoped-out-agent is excluded (Scope: **/*.py doesn't match .md).
        assert agents == ["full-file-agent"]
        assert file_tokens == 400 // mfd.BYTES_PER_TOKEN_ESTIMATE
        assert lens_warnings == []
        assert file_missing is False

    def test_missing_file_is_flagged_not_silently_zeroed(self, tmp_path):
        agents_dir, registry_path = _minimal_roster(tmp_path)
        roster, _warnings = mfd.select_lenses.build_review_roster(agents_dir, registry_path)
        missing = tmp_path / "does-not-exist.md"

        agents, file_tokens, _lens_warnings, file_missing = mfd.theoretical_full_file_agents(
            missing, roster, agents_dir
        )

        # The roster resolution itself is unaffected by the target file
        # being unreadable — an earlier version conflated "file missing"
        # with "zero-byte file", both reading as file_tokens == 1.
        assert agents == ["full-file-agent"]
        assert file_missing is True
        assert file_tokens == 0


# ---------------------------------------------------------------------------
# collect_agent_dispatches — newer sibling-subagent-file layout
# ---------------------------------------------------------------------------


def _usage_record(ts: str, input_tokens: int, cache_creation: int = 0, cache_read: int = 0):
    return {
        "timestamp": ts,
        "message": {
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 5,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            }
        },
    }


def _sibling_transcript(tmp_path):
    """Shared arrange step for TestCollectAgentDispatchesSiblingLayout — an
    empty main transcript plus its sibling subagents/ directory, already
    created. Extracted after a test-smell-review finding on an earlier
    version flagged this four-line block as copy-pasted across three tests."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    subagents_dir = tmp_path / "session" / "subagents"
    subagents_dir.mkdir(parents=True)
    return transcript, subagents_dir


def _write_sibling_agent(subagents_dir, agent_id, agent_type, records):
    if agent_type is not None:
        (subagents_dir / f"agent-{agent_id}.meta.json").write_text(
            json.dumps({"agentType": agent_type}), encoding="utf-8"
        )
    (subagents_dir / f"agent-{agent_id}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records), encoding="utf-8"
    )


class TestCollectAgentDispatchesSiblingLayout:
    def test_sums_input_side_fields_per_agent(self, tmp_path):
        transcript, subagents_dir = _sibling_transcript(tmp_path)
        _write_sibling_agent(
            subagents_dir,
            "abc",
            "dev-team:correctness-review",
            [
                _usage_record("2026-08-01T19:00:00.000Z", input_tokens=10, cache_creation=900),
                _usage_record("2026-08-01T19:00:02.000Z", input_tokens=5),
            ],
        )

        dispatches = mfd.collect_agent_dispatches(transcript)

        assert dispatches == [
            {
                "agent_type": "dev-team:correctness-review",
                "timestamp": "2026-08-01T19:00:00.000Z",
                "input_spend": 10 + 900 + 5,
            }
        ]

    def test_multiple_agents_sorted_by_timestamp(self, tmp_path):
        transcript, subagents_dir = _sibling_transcript(tmp_path)
        _write_sibling_agent(
            subagents_dir,
            "later",
            "dev-team:naming-review",
            [_usage_record("2026-08-01T19:05:00.000Z", input_tokens=1)],
        )
        _write_sibling_agent(
            subagents_dir,
            "earlier",
            "dev-team:doc-review",
            [_usage_record("2026-08-01T19:00:00.000Z", input_tokens=1)],
        )

        dispatches = mfd.collect_agent_dispatches(transcript)
        assert [d["agent_type"] for d in dispatches] == [
            "dev-team:doc-review",
            "dev-team:naming-review",
        ]

    def test_no_subagents_dir_falls_back_to_empty(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text("", encoding="utf-8")
        assert mfd.collect_agent_dispatches(transcript) == []

    def test_meta_json_missing_agent_type_falls_back_to_attribution_agent(self, tmp_path):
        # A review round found the sibling-layout parser required
        # `.meta.json`'s `agentType` with no fallback, unlike
        # cost_meter._agent_type_key's documented attributionAgent-primary
        # precedence. This pins the fallback.
        transcript, subagents_dir = _sibling_transcript(tmp_path)
        (subagents_dir / "agent-xyz.meta.json").write_text(
            json.dumps({"agentType": None}), encoding="utf-8"
        )
        record = _usage_record("2026-08-01T19:00:00.000Z", input_tokens=1)
        record["attributionAgent"] = "dev-team:security-review"
        (subagents_dir / "agent-xyz.jsonl").write_text(json.dumps(record), encoding="utf-8")

        dispatches = mfd.collect_agent_dispatches(transcript)
        assert dispatches == [
            {
                "agent_type": "dev-team:security-review",
                "timestamp": "2026-08-01T19:00:00.000Z",
                "input_spend": 1,
            }
        ]

    def test_no_meta_json_sidecar_still_discovered_via_jsonl_glob(self, tmp_path):
        # An earlier version discovered sibling agents by globbing
        # `agent-*.meta.json`, silently finding zero dispatches for any
        # session whose harness version doesn't write that sidecar. This
        # pins discovery via `agent-*.jsonl` instead, with the
        # attributionAgent fallback covering the missing sidecar.
        transcript, subagents_dir = _sibling_transcript(tmp_path)
        record = _usage_record("2026-08-01T19:00:00.000Z", input_tokens=7)
        record["attributionAgent"] = "dev-team:structure-review"
        (subagents_dir / "agent-noMeta.jsonl").write_text(
            json.dumps(record), encoding="utf-8"
        )

        dispatches = mfd.collect_agent_dispatches(transcript)
        assert dispatches == [
            {
                "agent_type": "dev-team:structure-review",
                "timestamp": "2026-08-01T19:00:00.000Z",
                "input_spend": 7,
            }
        ]

    def test_top_level_usage_is_also_summed(self, tmp_path):
        # cost_meter._first_present_field checks both a record's top level
        # AND message.usage; an earlier version of this script's usage
        # extraction checked only message.usage.
        transcript, subagents_dir = _sibling_transcript(tmp_path)
        record = {
            "timestamp": "2026-08-01T19:00:00.000Z",
            "usage": {"input_tokens": 42, "output_tokens": 1},
        }
        _write_sibling_agent(subagents_dir, "abc", "dev-team:correctness-review", [record])

        dispatches = mfd.collect_agent_dispatches(transcript)
        assert dispatches[0]["input_spend"] == 42

    def test_chronological_not_lexicographic_sort(self, tmp_path):
        # A mixed-offset-style timestamp pair where lexicographic order
        # diverges from chronological order: '+' (0x2B) sorts before 'Z'
        # (0x5A), but 19:00:00+02:00 is actually LATER in absolute time
        # than 19:00:00Z minus the naive same-clock-reading comparison
        # would suggest — use two unambiguous instants instead, one with an
        # explicit offset that is chronologically earlier despite having a
        # lexicographically larger timestamp string.
        transcript, subagents_dir = _sibling_transcript(tmp_path)
        _write_sibling_agent(
            subagents_dir,
            "zzz_but_earlier",
            "dev-team:naming-review",
            [_usage_record("2026-08-01T09:00:00.000+00:00", input_tokens=1)],
        )
        _write_sibling_agent(
            subagents_dir,
            "aaa_but_later",
            "dev-team:doc-review",
            [_usage_record("2026-08-01T08:00:00.000Z", input_tokens=1)],
        )
        # Lexicographically: "...+00:00" < "...Z" is false ('+' < 'Z' is
        # true, so "09:00:00.000+00:00" actually sorts BEFORE
        # "08:00:00.000Z" as raw strings, even though 08:00Z is chronologically
        # earlier) — this is exactly the divergence a string sort misses.
        dispatches = mfd.collect_agent_dispatches(transcript)
        assert [d["agent_type"] for d in dispatches] == [
            "dev-team:doc-review",
            "dev-team:naming-review",
        ]


# ---------------------------------------------------------------------------
# collect_agent_dispatches — older inline-isSidechain layout
# ---------------------------------------------------------------------------


def _task_dispatch_lines(tool_use_id, agent_id, subagent_type, ts_dispatch, ts_result):
    return [
        {
            "timestamp": ts_dispatch,
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": "Task",
                        "input": {"subagent_type": subagent_type},
                    }
                ]
            },
        },
        {
            "timestamp": ts_result,
            "toolUseResult": {"agentId": agent_id},
            "message": {"content": [{"type": "tool_result", "tool_use_id": tool_use_id}]},
        },
    ]


class TestCollectAgentDispatchesInlineLayout:
    def test_joins_dispatch_and_usage_via_agent_id(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        lines = _task_dispatch_lines(
            "toolu_1", "agent-1", "dev-team:security-review",
            "2026-08-01T19:00:00.000Z", "2026-08-01T19:00:01.000Z",
        ) + [
            {
                "timestamp": "2026-08-01T19:00:02.000Z",
                "isSidechain": True,
                "agentId": "agent-1",
                "message": {"usage": {"input_tokens": 42, "output_tokens": 1}},
            },
        ]
        transcript.write_text(
            "\n".join(json.dumps(line) for line in lines), encoding="utf-8"
        )

        dispatches = mfd.collect_agent_dispatches(transcript)

        assert dispatches == [
            {
                "agent_type": "dev-team:security-review",
                "timestamp": "2026-08-01T19:00:02.000Z",
                "input_spend": 42,
            }
        ]

    def test_multiple_agents_sorted_by_timestamp(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        lines = (
            _task_dispatch_lines(
                "toolu_later", "agent-later", "dev-team:naming-review",
                "2026-08-01T19:05:00.000Z", "2026-08-01T19:05:01.000Z",
            )
            + [
                {
                    "timestamp": "2026-08-01T19:05:02.000Z",
                    "isSidechain": True,
                    "agentId": "agent-later",
                    "message": {"usage": {"input_tokens": 1}},
                }
            ]
            + _task_dispatch_lines(
                "toolu_earlier", "agent-earlier", "dev-team:doc-review",
                "2026-08-01T19:00:00.000Z", "2026-08-01T19:00:01.000Z",
            )
            + [
                {
                    "timestamp": "2026-08-01T19:00:02.000Z",
                    "isSidechain": True,
                    "agentId": "agent-earlier",
                    "message": {"usage": {"input_tokens": 1}},
                }
            ]
        )
        transcript.write_text(
            "\n".join(json.dumps(line) for line in lines), encoding="utf-8"
        )

        dispatches = mfd.collect_agent_dispatches(transcript)
        assert [d["agent_type"] for d in dispatches] == [
            "dev-team:doc-review",
            "dev-team:naming-review",
        ]

    def test_dispatched_agent_with_no_usage_record_defaults_to_zero_spend(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        lines = _task_dispatch_lines(
            "toolu_1", "agent-1", "dev-team:structure-review",
            "2026-08-01T19:00:00.000Z", "2026-08-01T19:00:01.000Z",
        ) + [
            # A sidechain record with a timestamp but no usage-bearing
            # message — the agent was dispatched and its first-record
            # timestamp is known, but no usage arrived (e.g. it errored
            # before producing billable output).
            {
                "timestamp": "2026-08-01T19:00:02.000Z",
                "isSidechain": True,
                "agentId": "agent-1",
                "message": {},
            },
        ]
        transcript.write_text(
            "\n".join(json.dumps(line) for line in lines), encoding="utf-8"
        )

        dispatches = mfd.collect_agent_dispatches(transcript)
        assert dispatches == [
            {
                "agent_type": "dev-team:structure-review",
                "timestamp": "2026-08-01T19:00:02.000Z",
                "input_spend": 0,
            }
        ]

    def test_attribution_agent_used_when_dispatch_join_is_unavailable(self, tmp_path):
        # An earlier version sourced agent_type ONLY from the Task/Agent
        # dispatch join, silently dropping any sidechain agent attributed
        # via the native attributionAgent field with no recoverable join
        # (cost_meter.py documents attributionAgent as the PRIMARY signal,
        # the join as the fallback).
        transcript = tmp_path / "session.jsonl"
        lines = [
            {
                "timestamp": "2026-08-01T19:00:00.000Z",
                "isSidechain": True,
                "agentId": "agent-orphan",
                "attributionAgent": "dev-team:domain-review",
                "message": {"usage": {"input_tokens": 5}},
            }
        ]
        transcript.write_text(
            "\n".join(json.dumps(line) for line in lines), encoding="utf-8"
        )

        dispatches = mfd.collect_agent_dispatches(transcript)
        assert dispatches == [
            {
                "agent_type": "dev-team:domain-review",
                "timestamp": "2026-08-01T19:00:00.000Z",
                "input_spend": 5,
            }
        ]


# ---------------------------------------------------------------------------
# _round_report_row — the aggregation cmd_report is built on
# ---------------------------------------------------------------------------


class TestRoundReportRow:
    def test_counts_agent_instances_not_distinct_types(self):
        # The core correctness-review finding on an earlier version: two
        # dispatches of the SAME agent type in one round are two
        # independent full-file re-reads, not one — a set-based
        # intersection collapsed them to one and understated the estimate.
        round_dispatches = [
            _d("dev-team:correctness-review", "2026-08-01T19:00:00.000Z", spend=1000),
            _d("dev-team:correctness-review", "2026-08-01T19:00:02.000Z", spend=1000),
            _d("dev-team:naming-review", "2026-08-01T19:00:04.000Z", spend=1000),
        ]
        per_file = {
            "some.md": (["correctness-review", "naming-review"], 500, [], False)
        }

        row = mfd._round_report_row(round_dispatches, per_file)

        assert row["files"][0]["n_full_file_agents_dispatched"] == 3
        assert row["files"][0]["avoidable_tokens_estimate"] == 500 * 2  # (3 - 1)

    def test_avoidable_pct_is_estimate_suffixed(self):
        round_dispatches = [
            _d("dev-team:correctness-review", "2026-08-01T19:00:00.000Z", spend=1000),
            _d("dev-team:naming-review", "2026-08-01T19:00:02.000Z", spend=1000),
        ]
        per_file = {
            "some.md": (["correctness-review", "naming-review"], 200, [], False)
        }

        row = mfd._round_report_row(round_dispatches, per_file)

        assert "avoidable_pct_of_round_total_estimate" in row
        assert row["avoidable_pct_of_round_total_estimate"] == round(
            100 * 200 / 2000, 2
        )

    def test_zero_round_total_yields_none_percentage(self):
        round_dispatches = [_d("dev-team:correctness-review", "2026-08-01T19:00:00.000Z", spend=0)]
        per_file = {"some.md": (["correctness-review"], 100, [], False)}

        row = mfd._round_report_row(round_dispatches, per_file)
        assert row["avoidable_pct_of_round_total_estimate"] is None


# ---------------------------------------------------------------------------
# _filter_since
# ---------------------------------------------------------------------------


class TestFilterSince:
    def test_none_since_returns_all(self):
        dispatches = [_d("a", "2026-08-01T19:00:00.000Z")]
        assert mfd._filter_since(dispatches, None) == dispatches

    def test_drops_earlier_dispatches(self):
        dispatches = [
            _d("early", "2026-08-01T18:00:00.000Z"),
            _d("late", "2026-08-01T19:00:00.000Z"),
        ]
        filtered = mfd._filter_since(dispatches, "2026-08-01T18:30:00.000Z")
        assert [d["agent_type"] for d in filtered] == ["late"]

    def test_boundary_is_inclusive(self):
        # A mutation of the >= comparison to > would drop a dispatch that
        # fires at exactly `since` — this pins the inclusive boundary.
        dispatches = [_d("boundary", "2026-08-01T18:30:00.000Z")]
        filtered = mfd._filter_since(dispatches, "2026-08-01T18:30:00.000Z")
        assert filtered == dispatches


# ---------------------------------------------------------------------------
# Privacy boundary (security-review finding): never surface prompt text.
# ---------------------------------------------------------------------------


class TestPrivacyBoundary:
    def test_prompt_text_sentinel_never_appears_in_dispatch_output(self, tmp_path):
        transcript, subagents_dir = _sibling_transcript(tmp_path)
        sentinel = "SENTINEL-PROMPT-TEXT-SHOULD-NEVER-SURFACE"
        record = {
            "timestamp": "2026-08-01T19:00:00.000Z",
            "message": {
                "content": [{"type": "text", "text": sentinel}],
                "usage": {"input_tokens": 1},
            },
        }
        _write_sibling_agent(subagents_dir, "abc", "dev-team:correctness-review", [record])

        dispatches = mfd.collect_agent_dispatches(transcript)

        assert sentinel not in json.dumps(dispatches)
