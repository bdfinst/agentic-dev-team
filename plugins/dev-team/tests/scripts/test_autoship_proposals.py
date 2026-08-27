"""Tests for autoship_proposals.py — the three Step 2b/2c deterministic
transforms extracted from `skills/autoship/SKILL.md` prose (#2072):
validate_proposals (Step 2b response validation rules 1-4),
partition_and_filter_blocked (Step 2c Fix A + issue-number validation), and
parse_marker (confirmed_batch_members marker parse/validate)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import autoship_proposals


def _entry(number: int, day: int, title: str = "Some issue") -> dict:
    return {
        "number": number,
        "title": title,
        "createdAt": f"2026-07-{day:02d}T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# is_valid_issue_number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (101, True),
        (0, True),
        ("101", True),
        ("0", True),
        (-1, False),
        ("-1", False),
        (1.5, False),
        ("1.5", False),
        ("101abc", False),
        ("", False),
        (None, False),
        (True, False),  # bool is an int subclass — must be excluded explicitly
        ([101], False),
    ],
)
def test_is_valid_issue_number(value, expected) -> None:
    assert autoship_proposals.is_valid_issue_number(value) is expected


# ---------------------------------------------------------------------------
# validate_proposals — Step 2b response validation rules 1-4
# ---------------------------------------------------------------------------


def test_rule1_discards_issue_number_not_in_ungrouped_set() -> None:
    ungrouped = [_entry(101, 1), _entry(102, 2)]
    proposals = [{"rationale": "same feature", "issues": [101, 102, 999]}]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    assert result["batches"] == [{"rationale": "same feature", "issues": [101, 102]}]
    assert result["ungrouped"] == []


def test_rule2_discards_duplicate_keeping_first_occurrence() -> None:
    ungrouped = [_entry(101, 1), _entry(102, 2), _entry(103, 3)]
    proposals = [
        {"rationale": "first", "issues": [101, 102]},
        {"rationale": "second", "issues": [102, 103]},
    ]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    # The second proposal loses #102 to the first (rule 2), leaving it with
    # only #103 — fewer than 2 members, so rule 4 discards it entirely.
    assert result["batches"] == [{"rationale": "first", "issues": [101, 102]}]
    assert [e["number"] for e in result["ungrouped"]] == [103]


def test_rule3_trims_oversized_proposal_oldest_first_overflow_to_ungrouped() -> None:
    ungrouped = [_entry(80 + i, i + 1) for i in range(6)]
    proposals = [{"rationale": "big group", "issues": [80, 81, 82, 83, 84, 85]}]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    assert result["batches"] == [
        {"rationale": "big group", "issues": [80, 81, 82, 83, 84]}
    ]
    assert [e["number"] for e in result["ungrouped"]] == [85]


def test_rule3_trim_orders_by_createdat_not_input_order() -> None:
    # Issue numbers given out of createdAt order — trim must still keep the
    # 3 OLDEST by createdAt, not the first 3 listed in the proposal.
    ungrouped = [_entry(200, 3), _entry(201, 1), _entry(202, 2)]
    proposals = [{"rationale": "r", "issues": [200, 201, 202]}]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 2)

    assert result["batches"] == [{"rationale": "r", "issues": [201, 202]}]
    assert [e["number"] for e in result["ungrouped"]] == [200]


def test_rule4_discards_proposal_with_fewer_than_two_members() -> None:
    ungrouped = [_entry(101, 1)]
    proposals = [{"rationale": "solo", "issues": [101]}]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    assert result["batches"] == []
    assert [e["number"] for e in result["ungrouped"]] == [101]


def test_rule4_discard_after_rule1_strips_invented_member() -> None:
    # #999 is invented (not in ungrouped) — after rule 1 discards it, only
    # #101 remains, which is fewer than 2 — rule 4 discards the proposal.
    ungrouped = [_entry(101, 1)]
    proposals = [{"rationale": "r", "issues": [101, 999]}]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    assert result["batches"] == []
    assert [e["number"] for e in result["ungrouped"]] == [101]


def test_empty_proposals_list_leaves_everything_ungrouped() -> None:
    ungrouped = [_entry(101, 1), _entry(102, 2)]

    result = autoship_proposals.validate_proposals([], ungrouped, 5)

    assert result["batches"] == []
    assert result["ungrouped"] == ungrouped


def test_valid_proposal_at_exactly_two_members_survives() -> None:
    ungrouped = [_entry(101, 1), _entry(102, 2)]
    proposals = [{"rationale": "pair", "issues": [101, 102]}]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    assert result["batches"] == [{"rationale": "pair", "issues": [101, 102]}]
    assert result["ungrouped"] == []


def test_multiple_disjoint_proposals_all_survive() -> None:
    ungrouped = [_entry(n, n) for n in range(1, 5)]
    proposals = [
        {"rationale": "a", "issues": [1, 2]},
        {"rationale": "b", "issues": [3, 4]},
    ]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    assert result["batches"] == [
        {"rationale": "a", "issues": [1, 2]},
        {"rationale": "b", "issues": [3, 4]},
    ]
    assert result["ungrouped"] == []


def test_missing_rationale_defaults_to_empty_string() -> None:
    ungrouped = [_entry(1, 1), _entry(2, 2)]
    proposals = [{"issues": [1, 2]}]

    result = autoship_proposals.validate_proposals(proposals, ungrouped, 5)

    assert result["batches"] == [{"rationale": "", "issues": [1, 2]}]


# ---------------------------------------------------------------------------
# _load_agent_response — Rule 5 (unparseable response -> zero proposals)
# ---------------------------------------------------------------------------


def test_unparseable_json_response_yields_zero_proposals() -> None:
    assert autoship_proposals._load_agent_response("not json at all") == []


def test_non_object_response_yields_zero_proposals() -> None:
    assert autoship_proposals._load_agent_response("[1, 2, 3]") == []


def test_missing_proposals_key_yields_zero_proposals() -> None:
    assert autoship_proposals._load_agent_response('{"other": []}') == []


def test_non_list_proposals_value_yields_zero_proposals() -> None:
    assert autoship_proposals._load_agent_response('{"proposals": "oops"}') == []


def test_well_formed_response_parses_proposals() -> None:
    raw = json.dumps({"proposals": [{"rationale": "r", "issues": [1, 2]}]})
    assert autoship_proposals._load_agent_response(raw) == [
        {"rationale": "r", "issues": [1, 2]}
    ]


def test_empty_proposals_array_is_a_valid_response() -> None:
    assert autoship_proposals._load_agent_response('{"proposals": []}') == []


def test_non_dict_proposal_entry_is_skipped() -> None:
    raw = json.dumps({"proposals": ["not-an-object", {"rationale": "r", "issues": [1, 2]}]})
    assert autoship_proposals._load_agent_response(raw) == [
        {"rationale": "r", "issues": [1, 2]}
    ]


def test_proposal_with_non_list_issues_is_skipped() -> None:
    raw = json.dumps({"proposals": [{"rationale": "r", "issues": "oops"}]})
    assert autoship_proposals._load_agent_response(raw) == []


# ---------------------------------------------------------------------------
# partition_and_filter_blocked — Step 2c Fix A + issue-number validation
# ---------------------------------------------------------------------------


def test_valid_batch_is_blocked_and_removed_from_ungrouped() -> None:
    ungrouped = [_entry(101, 1), _entry(102, 2), _entry(103, 3)]
    batches = [{"rationale": "r", "issues": [101, 102]}]

    result = autoship_proposals.partition_and_filter_blocked(ungrouped, batches)

    assert result["blocked_batches"] == batches
    assert result["rejected_batches"] == []
    assert [e["number"] for e in result["ungrouped"]] == [103]


def test_batch_with_invalid_issue_number_is_rejected_entirely() -> None:
    ungrouped = [_entry(101, 1), _entry(102, 2)]
    batches = [{"rationale": "r", "issues": [101, "102; rm -rf /"]}]

    result = autoship_proposals.partition_and_filter_blocked(ungrouped, batches)

    assert result["blocked_batches"] == []
    assert result["rejected_batches"] == batches
    # Rejected batch's members MUST stay in ungrouped — never removed.
    assert [e["number"] for e in result["ungrouped"]] == [101, 102]


def test_mixed_valid_and_invalid_batches_partition_independently() -> None:
    ungrouped = [_entry(1, 1), _entry(2, 2), _entry(3, 3), _entry(4, 4)]
    valid_batch = {"rationale": "good", "issues": [1, 2]}
    invalid_batch = {"rationale": "bad", "issues": [3, "4x"]}
    batches = [valid_batch, invalid_batch]

    result = autoship_proposals.partition_and_filter_blocked(ungrouped, batches)

    assert result["blocked_batches"] == [valid_batch]
    assert result["rejected_batches"] == [invalid_batch]
    # Only the valid batch's members (#1, #2) are removed; #3/#4 stay.
    assert [e["number"] for e in result["ungrouped"]] == [3, 4]


def test_no_batches_leaves_ungrouped_untouched() -> None:
    ungrouped = [_entry(1, 1), _entry(2, 2)]

    result = autoship_proposals.partition_and_filter_blocked(ungrouped, [])

    assert result["blocked_batches"] == []
    assert result["rejected_batches"] == []
    assert result["ungrouped"] == ungrouped


# ---------------------------------------------------------------------------
# parse_marker — confirmed_batch_members marker parse/validate
# ---------------------------------------------------------------------------


def _comment(login: str, body: str) -> dict:
    return {"author": {"login": login}, "body": body}


def test_parse_marker_extracts_valid_values() -> None:
    comments = [
        _comment(
            "the-bot",
            "Rationale text\n\n<!-- autoship-batch-members: 101,102,103 -->",
        )
    ]

    assert autoship_proposals.parse_marker(comments, "the-bot") == [101, 102, 103]


def test_parse_marker_ignores_comment_from_different_author() -> None:
    comments = [
        _comment("some-attacker", "<!-- autoship-batch-members: 101,102 -->")
    ]

    assert autoship_proposals.parse_marker(comments, "the-bot") is None


def test_parse_marker_returns_none_when_no_comment_matches() -> None:
    assert autoship_proposals.parse_marker([], "the-bot") is None


def test_parse_marker_drops_whole_marker_on_any_invalid_value() -> None:
    comments = [
        _comment("the-bot", "<!-- autoship-batch-members: 101,not-a-number -->")
    ]

    assert autoship_proposals.parse_marker(comments, "the-bot") is None


def test_parse_marker_most_recent_match_wins() -> None:
    # Two comments from the same author — gh returns oldest-first, so the
    # LAST one in the array is the most recent and must win.
    comments = [
        _comment("the-bot", "<!-- autoship-batch-members: 101,102 -->"),
        _comment("the-bot", "<!-- autoship-batch-members: 101,102,103 -->"),
    ]

    assert autoship_proposals.parse_marker(comments, "the-bot") == [101, 102, 103]


def test_parse_marker_ignores_comments_without_the_marker() -> None:
    comments = [
        _comment("the-bot", "just a regular comment, no marker here"),
        _comment("the-bot", "<!-- autoship-batch-members: 5,6 -->"),
    ]

    assert autoship_proposals.parse_marker(comments, "the-bot") == [5, 6]


def test_parse_marker_handles_empty_value_list() -> None:
    comments = [_comment("the-bot", "<!-- autoship-batch-members:  -->")]

    assert autoship_proposals.parse_marker(comments, "the-bot") is None


def test_parse_marker_author_missing_login_field_never_matches() -> None:
    comments = [{"author": {}, "body": "<!-- autoship-batch-members: 1,2 -->"}]

    assert autoship_proposals.parse_marker(comments, "the-bot") is None


def test_parse_marker_author_field_absent_never_matches() -> None:
    comments = [{"body": "<!-- autoship-batch-members: 1,2 -->"}]

    assert autoship_proposals.parse_marker(comments, "the-bot") is None


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_build_parser_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit):
        autoship_proposals.build_parser().parse_args([])


def test_build_parser_validate_proposals_defaults() -> None:
    args = autoship_proposals.build_parser().parse_args(
        [
            "validate-proposals",
            "--agent-response-file",
            "resp.json",
            "--ungrouped-file",
            "scratch.json",
        ]
    )
    assert args.command == "validate-proposals"
    assert args.max_batch_size == 5


def test_main_validate_proposals_end_to_end(tmp_path) -> None:
    ungrouped_file = tmp_path / "scratch.json"
    ungrouped_file.write_text(
        json.dumps({"batches": [], "ungrouped": [_entry(101, 1), _entry(102, 2)]}),
        encoding="utf-8",
    )
    response_file = tmp_path / "response.json"
    response_file.write_text(
        json.dumps({"proposals": [{"rationale": "r", "issues": [101, 102]}]}),
        encoding="utf-8",
    )

    exit_code = autoship_proposals.main(
        [
            "validate-proposals",
            "--agent-response-file",
            str(response_file),
            "--ungrouped-file",
            str(ungrouped_file),
        ]
    )

    assert exit_code == 0


def test_main_validate_proposals_accepts_bare_ungrouped_array_file(tmp_path) -> None:
    # --ungrouped-file may point at a bare array, not just the full scratch
    # object — _load_ungrouped must tolerate both shapes.
    ungrouped_file = tmp_path / "ungrouped.json"
    ungrouped_file.write_text(json.dumps([_entry(101, 1)]), encoding="utf-8")
    response_file = tmp_path / "response.json"
    response_file.write_text(json.dumps({"proposals": []}), encoding="utf-8")

    exit_code = autoship_proposals.main(
        [
            "validate-proposals",
            "--agent-response-file",
            str(response_file),
            "--ungrouped-file",
            str(ungrouped_file),
        ]
    )

    assert exit_code == 0


def test_main_remove_blocked_end_to_end(tmp_path) -> None:
    ungrouped_file = tmp_path / "scratch.json"
    ungrouped_file.write_text(
        json.dumps({"ungrouped": [_entry(1, 1), _entry(2, 2), _entry(3, 3)]}),
        encoding="utf-8",
    )
    batches_file = tmp_path / "batches.json"
    batches_file.write_text(
        json.dumps([{"rationale": "r", "issues": [1, 2]}]), encoding="utf-8"
    )

    exit_code = autoship_proposals.main(
        [
            "remove-blocked",
            "--ungrouped-file",
            str(ungrouped_file),
            "--batches-file",
            str(batches_file),
        ]
    )

    assert exit_code == 0


def test_main_remove_blocked_malformed_batches_file_errors(tmp_path, capsys) -> None:
    ungrouped_file = tmp_path / "scratch.json"
    ungrouped_file.write_text(json.dumps({"ungrouped": []}), encoding="utf-8")
    batches_file = tmp_path / "batches.json"
    batches_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    exit_code = autoship_proposals.main(
        [
            "remove-blocked",
            "--ungrouped-file",
            str(ungrouped_file),
            "--batches-file",
            str(batches_file),
        ]
    )

    assert exit_code == 1
    assert "autoship_proposals:" in capsys.readouterr().err


def test_main_parse_marker_end_to_end(tmp_path) -> None:
    comments_file = tmp_path / "comments.json"
    comments_file.write_text(
        json.dumps([_comment("the-bot", "<!-- autoship-batch-members: 1,2 -->")]),
        encoding="utf-8",
    )

    exit_code = autoship_proposals.main(
        [
            "parse-marker",
            "--comments-file",
            str(comments_file),
            "--invoking-login",
            "the-bot",
        ]
    )

    assert exit_code == 0


def test_main_missing_ungrouped_key_in_object_errors(tmp_path, capsys) -> None:
    ungrouped_file = tmp_path / "scratch.json"
    ungrouped_file.write_text(json.dumps({"batches": []}), encoding="utf-8")
    response_file = tmp_path / "response.json"
    response_file.write_text(json.dumps({"proposals": []}), encoding="utf-8")

    exit_code = autoship_proposals.main(
        [
            "validate-proposals",
            "--agent-response-file",
            str(response_file),
            "--ungrouped-file",
            str(ungrouped_file),
        ]
    )

    assert exit_code == 1
    assert "autoship_proposals:" in capsys.readouterr().err


def test_main_unreadable_ungrouped_file_errors(tmp_path, capsys) -> None:
    response_file = tmp_path / "response.json"
    response_file.write_text(json.dumps({"proposals": []}), encoding="utf-8")

    exit_code = autoship_proposals.main(
        [
            "validate-proposals",
            "--agent-response-file",
            str(response_file),
            "--ungrouped-file",
            str(tmp_path / "does-not-exist.json"),
        ]
    )

    assert exit_code == 1
    assert "autoship_proposals:" in capsys.readouterr().err
