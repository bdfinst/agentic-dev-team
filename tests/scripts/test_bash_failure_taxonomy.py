"""Unit tests for scripts/bash_failure_taxonomy.py Step 1.1 (issue #2038):
self-contained Bash tool_use/tool_result pairing.

Covers exactly the Step 1.1 TEST list from the approved plan:
(a) a synthetic Bash tool_use + failing tool_result pair yields both texts
    together, (b) a successful Bash call is excluded, (c) a non-Bash tool's
    error is excluded, (d) an orphaned tool_result is reported unpaired
    rather than matched to an unrelated command, (e) a transcript file with
    one well-formed pair plus one corrupt (non-JSON) line still yields the
    well-formed pair and does not raise, (f) the script's
    `argparse.ArgumentParser` exposes exactly the attribute names
    `resolve_transcripts`/`resolve_all_transcripts` require, (g) a
    transcript line that decodes as valid JSON but is a non-dict value, or
    a dict missing `type`/`content`/`tool_use_id`, is skipped without
    raising -- mirroring `session_extract.py::_read_synced_records`'s
    `isinstance(rec, dict)` guard.

No import from `session_extract.py` beyond the two path-discovery
functions the plan names as reusable -- see the module docstring under
test for the privacy-contract rationale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import bash_failure_taxonomy as bft


def _assistant(blocks: list[dict]) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


def _user(blocks: list[dict]) -> dict:
    return {"type": "user", "message": {"role": "user", "content": blocks}}


def _tool_use(tool_id: str, name: str, command: str | None = None) -> dict:
    block = {"type": "tool_use", "id": tool_id, "name": name}
    if command is not None:
        block["input"] = {"command": command}
    return block


def _tool_result(tool_id: str, text: str, *, is_error: bool) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": text,
        "is_error": is_error,
    }


def _write_transcript(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) a synthetic Bash tool_use + failing tool_result pair yields both texts
# ---------------------------------------------------------------------------


def test_bash_error_paired_with_originating_command(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Bash", "grep foo bar.txt")]),
            _user([_tool_result("t1", "grep: bar.txt: No such file or directory", is_error=True)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.command == "grep foo bar.txt"
    assert pair.error_text == "grep: bar.txt: No such file or directory"
    assert pair.tool_use_id == "t1"
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (b) a successful Bash call is excluded
# ---------------------------------------------------------------------------


def test_successful_bash_call_excluded(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Bash", "ls")]),
            _user([_tool_result("t1", "file1\nfile2", is_error=False)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert result.pairs == []
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (c) a non-Bash tool's error is excluded
# ---------------------------------------------------------------------------


def test_non_bash_tool_error_excluded(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Edit")]),
            _user([_tool_result("t1", "old_string not found in file", is_error=True)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert result.pairs == []
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (d) an orphaned tool_result is reported unpaired, not matched to an
#     unrelated command
# ---------------------------------------------------------------------------


def test_orphaned_tool_result_reported_unpaired(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            # An unrelated, successfully-paired Bash command earlier in the
            # transcript -- the orphaned result below must NOT be matched to
            # this command's text.
            _assistant([_tool_use("t1", "Bash", "echo hello")]),
            _user([_tool_result("t1", "hello", is_error=False)]),
            # tool_use_id "t99" never appears as a tool_use in this
            # transcript (truncated/orphaned).
            _user([_tool_result("t99", "some error with no origin", is_error=True)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert result.pairs == []
    assert len(result.unpaired) == 1
    assert result.unpaired[0].tool_use_id == "t99"
    assert result.unpaired[0].error_text == "some error with no origin"


# ---------------------------------------------------------------------------
# (e) a corrupt (non-JSON) line does not abort the run
# ---------------------------------------------------------------------------


def test_corrupt_json_line_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    good_pair = [
        _assistant([_tool_use("t1", "Bash", "cat missing.txt")]),
        _user([_tool_result("t1", "cat: missing.txt: No such file or directory", is_error=True)]),
    ]
    lines = [json.dumps(r) for r in good_pair]
    lines.insert(1, "{not valid json,,,")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "cat missing.txt"
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (f) argparse.ArgumentParser attribute-name contract with
#     resolve_transcripts/resolve_all_transcripts
# ---------------------------------------------------------------------------


def test_arg_parser_exposes_attributes_resolve_functions_require(tmp_path):
    empty_root = tmp_path / "empty-projects-root"
    empty_root.mkdir()

    parser = bft.build_arg_parser()
    args = parser.parse_args(["--projects-root", str(empty_root)])

    # Must not raise AttributeError -- these functions duck-type on
    # args.transcript / args.project_dir / args.projects_root / args.cwd.
    assert bft.resolve_transcripts(args) == []
    assert bft.resolve_all_transcripts(args) == []


def test_arg_parser_transcript_flag_is_repeatable_and_attribute_named_transcript(tmp_path):
    transcript = tmp_path / "one.jsonl"
    _write_transcript(transcript, [])

    parser = bft.build_arg_parser()
    args = parser.parse_args(["--transcript", str(transcript)])

    assert args.transcript == [str(transcript)]
    assert bft.resolve_transcripts(args) == [Path(transcript)]


# ---------------------------------------------------------------------------
# (g) a malformed-but-JSON-valid record (non-dict, or a dict missing
#     type/content/tool_use_id) is skipped without raising
# ---------------------------------------------------------------------------


def test_non_dict_top_level_record_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    good_pair = [
        _assistant([_tool_use("t1", "Bash", "false")]),
        _user([_tool_result("t1", "command exited with a real error message", is_error=True)]),
    ]
    lines = [json.dumps(r) for r in good_pair]
    # A record that decodes as valid JSON but is not a dict (a bare array).
    lines.insert(1, json.dumps([1, 2, 3]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "false"
    assert result.unpaired == []


def test_tool_result_block_missing_required_fields_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        _assistant([_tool_use("t1", "Bash", "false")]),
        # A tool_result-shaped block missing both "content" and
        # "tool_use_id" -- must be skipped, not raise, and not appear as
        # either a pair or an unpaired result.
        _user([{"type": "tool_result", "is_error": True}]),
        _user([_tool_result("t1", "command exited with a real error message", is_error=True)]),
    ]
    _write_transcript(path, records)

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "false"
    assert result.unpaired == []
