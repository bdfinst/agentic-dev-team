"""Instrument audit and shared reader for the benefit evaluation.

Covers scripts/lib/benefit_eval/streams.py (reader, real-session filter,
window helpers, audit) and prereg.py (pre-registration parser), plus the
audit CLI in scripts/benefit_eval_cli.py.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from _benefit_baseline_rules import verdict_paragraph
from _benefit_eval_support import (
    LONG_ID,
    REAL_PREREG,
    World,
    cli_argv,
    load_cli,
    prereg_block_span,
    real_prereg_document,
)
from benefit_eval import prereg, streams

from _repo_root import REPO_ROOT


def metric(instrument: str, metric_id: str = "m1"):
    return SimpleNamespace(id=metric_id, instrument=instrument)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def audit_one(world: World, instrument: str = "ledger-skips") -> streams.InstrumentStatus:
    (status,) = streams.audit([metric(instrument)], world.sources)
    return status


# --- real-session count decides confirmed or gap -----------------------------


@pytest.mark.parametrize(
    ("sessions", "status", "code"),
    [(0, "gap", 1), (2, "gap", 1), (3, "confirmed", 0)],
)
def test_real_session_count_decides_confirmed_or_gap(world, sessions, status, code):
    world.real_sessions("ledger-skips", sessions)
    result = audit_one(world)
    assert result.status == status
    assert streams.audit_exit_code([result]) == code


def test_duplicate_rows_from_one_session_count_as_one_session(world):
    world.real_sessions("ledger-skips", 1, extra_rows=10)
    result = audit_one(world)
    assert (result.rows, result.real_sessions) == (11, 1)


def test_absent_instrument_file_is_a_gap(world):
    assert audit_one(world, "checkpoint-aborts").status == "gap"


# --- project roots and layout -----------------------------------------------


def test_sessions_from_two_project_roots_merge_into_one_count(world):
    world.real_sessions("ledger-skips", 2, extra_rows=0)
    other = world.add_project("other-project")
    world.session("sess-other")
    (other / ".claude" / "metrics" / "ledger-skips.jsonl").write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "session_id": "sess-other"}) + "\n"
    )
    result = audit_one(world)
    assert (result.status, result.real_sessions, result.rows) == ("confirmed", 3, 3)


def test_the_same_project_root_given_twice_is_read_once(world):
    world.real_sessions("ledger-skips", 2)
    once = audit_one(world)
    doubled = streams.Sources((world.project, world.project), world.home, world.projects)
    (twice,) = streams.audit([metric("ledger-skips")], doubled)
    assert twice == once


def test_legacy_layout_stream_is_read_in_place_and_never_moved(world):
    world.real_sessions("ledger-skips", 3, extra_rows=0)
    legacy = world.project / "metrics"
    legacy.mkdir()
    shutil.move(world.metrics_file("ledger-skips.jsonl"), legacy / "ledger-skips.jsonl")
    before = world.snapshot()
    result = audit_one(world)
    assert (result.status, result.real_sessions) == ("confirmed", 3)
    assert world.snapshot() == before
    assert not world.metrics_file("ledger-skips.jsonl").exists()


def test_current_layout_stream_wins_over_a_legacy_copy(world):
    world.real_sessions("ledger-skips", 3, extra_rows=0)
    legacy = world.project / "metrics"
    legacy.mkdir()
    (legacy / "ledger-skips.jsonl").write_text("not json\n")
    assert audit_one(world).status == "confirmed"


# --- unverified rows ---------------------------------------------------------


def test_rows_without_id_or_transcript_are_unverified_and_never_real(world):
    rows = [{"ts": "2026-01-01T00:00:00Z"}] * 4
    rows += [{"ts": "2026-01-01T00:00:00Z", "session_id": "no-transcript"}] * 2
    world.stream("ledger-skips", rows)
    result = audit_one(world)
    assert (result.unverified_rows, result.real_sessions, result.status) == (6, 0, "gap")


def test_unparseable_transcript_is_a_counted_skip_not_a_real_session(world):
    world.real_sessions("ledger-skips", 3, extra_rows=0)
    baseline = audit_one(world)
    path = world.metrics_file("ledger-skips.jsonl")
    path.write_text(
        path.read_text() + json.dumps({"ts": "2026-01-01T00:00:00Z", "session_id": "bad-transcript"}) + "\n"
    )
    world.session("bad-transcript", "this is not json\n")
    result = audit_one(world)
    assert (result.skipped_transcripts, result.real_sessions) == (1, 3)
    assert result.status == baseline.status


@pytest.mark.parametrize(
    "content",
    [
        '{"type":"user"}\nnot json\n',
        "[1]\n",
        'not json\n{"type":"user"}\n',
        '{"type":"user"}\n[1]\n',
    ],
    ids=["valid-then-garbage", "non-object-first", "garbage-then-valid", "valid-then-non-object"],
)
def test_transcript_with_an_undecodable_line_or_non_object_record_is_a_counted_skip(world, content):
    world.stream("ledger-skips", [{"ts": "2026-01-01T00:00:00Z", "session_id": "sess-x"}])
    world.session("sess-x", content)
    result = audit_one(world)
    assert (result.real_sessions, result.skipped_transcripts) == (0, 1)


def test_empty_transcript_is_not_a_real_session(world):
    world.stream("ledger-skips", [{"ts": "2026-01-01T00:00:00Z", "session_id": "sess-x"}])
    world.session("sess-x", "")
    result = audit_one(world)
    assert (result.real_sessions, result.unverified_rows) == (0, 1)


def test_subagent_transcript_does_not_make_a_session_real(world):
    sub = world.projects / "proj-a" / "sess0000-aaaa" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.jsonl").write_text('{"type":"user"}\n')
    world.stream("ledger-skips", [{"ts": "2026-01-01T00:00:00Z", "session_id": "agent-abc"}])
    assert audit_one(world).real_sessions == 0


def test_a_transcript_is_opened_once_to_decide_whether_it_is_real(world, monkeypatch):
    world.session("sess-x", '{"type":"user"}\n' * 3)
    transcript = world.projects / "proj-a" / "sess-x.jsonl"
    opened = []
    real_open = Path.open

    def counting_open(self, *args, **kwargs):
        opened.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    assert streams.SessionIndex(world.projects).classify("sess-x") == streams.SESSION_REAL
    assert opened.count(transcript) == 1


# --- identity classes --------------------------------------------------------


def test_id_less_stream_reports_no_session_ids_and_is_never_confirmed(world):
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z", "transcript": "x.jsonl"}] * 5)
    result = audit_one(world, "cost-metering")
    assert (result.status, result.real_sessions) == ("no session ids", 0)
    assert streams.audit_exit_code([result]) == 0


def test_id_less_json_file_without_session_ids_reports_no_session_ids(world):
    (world.home / "artifact-usage.json").write_text(
        json.dumps({"source-verification": {"use_count": 3, "last_used_at": "2026-01-01T00:00:00Z"}})
    )
    result = audit_one(world, "artifact-usage")
    assert (result.status, result.rows) == ("no session ids", 1)


def test_id_less_stream_with_no_rows_is_a_gap(world):
    assert audit_one(world, "cost-metering").status == "gap"


def test_metric_without_a_persisted_instrument_is_flagged_and_exits_1(world):
    result = audit_one(world, "none")
    assert (result.status, result.metrics) == ("no instrument", ("m1",))
    assert streams.audit_exit_code([result]) == 1


def test_manual_input_instrument_is_reported_manual_and_is_not_a_finding(world):
    result = audit_one(world, "manual-input")
    assert result.status == "manual"
    assert streams.audit_exit_code([result]) == 0


def test_subagent_transcripts_of_three_real_sessions_confirm_that_instrument(world):
    for i in range(3):
        world.session(f"sess-{i}")
        world.subagent(f"sess-{i}", "a1", [{"type": "assistant"}])
    result = audit_one(world, streams.SUBAGENT_TRANSCRIPTS)
    assert (result.status, result.real_sessions, result.rows) == ("confirmed", 3, 3)


def test_subagent_transcripts_of_a_session_without_a_real_transcript_are_unverified(world):
    for i in range(2):
        world.session(f"sess-{i}")
        world.subagent(f"sess-{i}", "a1", [{"type": "assistant"}])
    world.subagent("ghost", "a1", [{"type": "assistant"}])
    world.session("bad", "not json\n")
    world.subagent("bad", "a1", [{"type": "assistant"}])
    result = audit_one(world, streams.SUBAGENT_TRANSCRIPTS)
    assert (result.status, result.real_sessions, result.unverified_rows, result.skipped_transcripts) == ("gap", 2, 2, 1)


def test_no_subagent_transcripts_is_a_gap(world):
    assert audit_one(world, streams.SUBAGENT_TRANSCRIPTS).status == "gap"


@pytest.mark.parametrize("name", sorted(streams.instrument_log.STREAMS))
def test_rows_that_instrument_log_persists_carry_a_session_id_and_are_id_bearing(tmp_path, name):
    project = tmp_path / "project"
    project.mkdir()
    assert streams.instrument_log.append_row(name, {"event": "x"}, cwd=project, session_id=LONG_ID)
    sources = streams.Sources((project,), tmp_path / "home", tmp_path / "projects")
    rows = streams.load_rows(streams.STREAM_TABLE[name], sources)
    assert [row.data.get("session_id") for row in rows] == [LONG_ID]
    assert streams.STREAM_TABLE[name].identity_class == streams.ID_BEARING


def _run_consult_and_checkpoint(project: Path, session_id: str) -> None:
    scripts = REPO_ROOT / "plugins" / "dev-team" / "scripts"
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in streams.instrument_log.SESSION_ENV_VARS
    }
    env["CLAUDE_CODE_SESSION_ID"] = session_id
    (project / "a.py").write_text("x = 1\n")
    outcome = project / "outcome.json"
    outcome.write_text(
        json.dumps({"aborted": True, "redispatched": False, "findings": []})
    )
    for argv in (
        [
            scripts / "verdict_scope.py",
            "--root",
            project,
            "--lens-files",
            json.dumps({"correctness-review": ["a.py"]}),
        ],
        [scripts / "checkpoint_abort.py", "--mode", "outcome", "--from", outcome],
    ):
        subprocess.run(
            [sys.executable, *map(str, argv)],
            cwd=project,
            env=env,
            capture_output=True,
            check=True,
        )


@pytest.mark.parametrize("name", ["ledger-skips", "checkpoint-aborts"])
def test_consult_and_checkpoint_rows_from_three_real_sessions_are_confirmed(world, name):
    for i in range(3):
        session_id = f"sess{i:04d}-real"
        world.session(session_id)
        _run_consult_and_checkpoint(world.project, session_id)
    result = audit_one(world, name)
    assert (result.status, result.real_sessions) == ("confirmed", 3)


# --- unreadable instruments --------------------------------------------------


def test_non_json_line_names_file_line_and_next_action(world):
    path = world.metrics_file("ledger-skips.jsonl")
    path.write_text("not json\n")
    with pytest.raises(streams.InputError) as caught:
        audit_one(world)
    assert caught.value.message() == (
        f"{path}:1: line is not valid JSON. Next: repair or remove that line; "
        "the evaluation never edits the file"
    )


def test_valid_rows_then_a_bad_line_report_the_bad_line_number(world):
    path = world.metrics_file("ledger-skips.jsonl")
    path.write_text('{"ts":"2026-01-01T00:00:00Z"}\n\n{"ts":"2026-01-01T00:00:01Z"}\n{oops\n')
    with pytest.raises(streams.InputError) as caught:
        audit_one(world)
    assert caught.value.line == 4
    assert "Next:" in caught.value.message()


def test_unreadable_file_reports_line_zero(world):
    world.metrics_file("ledger-skips.jsonl").mkdir()
    with pytest.raises(streams.InputError) as caught:
        audit_one(world)
    assert caught.value.line == 0


def test_jsonl_line_that_is_not_an_object_names_file_line_and_next_action(world):
    path = world.metrics_file("ledger-skips.jsonl")
    path.write_text('{"ts":"2026-01-01T00:00:00Z"}\n[1]\n')
    with pytest.raises(streams.InputError) as caught:
        audit_one(world)
    assert caught.value.message() == (
        f"{path}:2: line is not a JSON object. Next: repair or remove that line; "
        "the evaluation never edits the file"
    )


def test_invalid_utf8_in_an_instrument_file_is_a_file_level_error(world):
    path = world.metrics_file("ledger-skips.jsonl")
    path.write_bytes(b'{"ts":"\xff"}\n')
    with pytest.raises(streams.InputError) as caught:
        audit_one(world)
    message = caught.value.message()
    assert message.startswith(f"{path}:0: cannot read file (UnicodeDecodeError). Next: ")


def test_invalid_json_in_artifact_usage_names_file_line_and_next_action(world):
    path = world.home / "artifact-usage.json"
    path.write_text('{"a": 1,\n "b": }')
    with pytest.raises(streams.InputError) as caught:
        audit_one(world, "artifact-usage")
    assert caught.value.message() == (
        f"{path}:2: file is not valid JSON. Next: repair the file; the evaluation never edits it"
    )


def test_json_file_that_is_not_an_object_is_malformed(world):
    (world.home / "artifact-usage.json").write_text("[1, 2]")
    with pytest.raises(streams.InputError, match=r"artifact-usage\.json:0: file is not a JSON object"):
        audit_one(world, "artifact-usage")


# --- session ids -------------------------------------------------------------


def test_listed_session_ids_are_truncated_to_eight_characters(world):
    world.session(LONG_ID)
    world.stream("ledger-skips", [{"ts": "2026-01-01T00:00:00Z", "session_id": LONG_ID}])
    result = audit_one(world)
    assert result.session_ids == (LONG_ID[:8],)
    assert LONG_ID not in repr(result)


# --- read-only ---------------------------------------------------------------


def test_audit_leaves_every_input_and_the_directory_listing_unchanged(world):
    world.real_sessions("ledger-skips", 3)
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z"}])
    (world.home / "artifact-usage.json").write_text('{"a":{"use_count":1}}')
    before = world.snapshot()
    statuses = streams.audit(
        [metric("ledger-skips"), metric("cost-metering"), metric("artifact-usage")], world.sources
    )
    assert {s.instrument: s.status for s in statuses} == {
        "ledger-skips": "confirmed",
        "cost-metering": "no session ids",
        "artifact-usage": "no session ids",
    }
    assert world.snapshot() == before


# --- window helpers ----------------------------------------------------------


def _rows(*stamps: str) -> list[streams.Row]:
    return [streams.Row(Path("f.jsonl"), i, {"ts": s}) for i, s in enumerate(stamps, 1)]


def test_boundary_row_falls_on_the_after_side_only():
    rows = _rows("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z")
    before, after = streams.split_at_boundary(rows, "ts", streams.parse_utc("2026-01-02T00:00:00Z"))
    assert (len(before), len(after)) == (1, 2)


def test_window_is_closed_at_start_and_open_at_end():
    rows = _rows("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z")
    kept = streams.rows_in_window(
        rows, "ts", streams.parse_utc("2026-01-01T00:00:00Z"), streams.parse_utc("2026-01-03T00:00:00Z")
    )
    assert [r.line for r in kept] == [1, 2]


@pytest.mark.parametrize("text", ["2026-01-01", "2026-01-01T00:00:00", "2026-01-01T00:00:00+00:00", ""])
def test_timestamp_without_z_suffix_is_rejected(text):
    with pytest.raises(ValueError):
        streams.parse_utc(text)


@pytest.mark.parametrize("text", ["2026-01-01T00:00:00.500Z", "2026-01-01T00:00:00.500000Z"])
def test_a_timestamp_with_three_or_six_fraction_digits_parses(text):
    assert streams.parse_utc(text).microsecond == 500000


@pytest.mark.parametrize(
    "text",
    ["2026-01-01T00:00:00.5Z", "2026-01-01T00:00:00.50Z", "2026-01-01T00:00:00.5000Z", "2026-01-01T00:00:00.Z"],
)
def test_a_timestamp_with_any_other_fraction_length_is_rejected_so_the_python_3_10_floor_holds(text):
    with pytest.raises(ValueError):
        streams.parse_utc(text)


def test_row_with_a_bad_timestamp_is_malformed_input_naming_its_line():
    with pytest.raises(streams.InputError) as caught:
        streams.rows_in_window(_rows("garbage"), "ts")
    assert caught.value.line == 1


# --- exit-code table ---------------------------------------------------------


def status_of(n, min_n, value, op="<=", limit=0.0, side_empty=False):
    outcome = streams.evaluate_status(n, min_n, value, streams.Threshold(op, limit), side_empty)
    return outcome.token, outcome.exit_code


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((0, 10, None, "<=", 5.0, True), ("no rows in window", 3)),
        ((4, 10, 1.0, "<=", 5.0), ("NULL (N=4)", 3)),
        ((4, 10, 1.0, "<=", 5.0, True), ("NULL (N=4)", 3)),
        ((10, 10, 1.0, "<=", 5.0), ("within", 0)),
        ((12, 10, 1.0, "<=", 5.0, True), ("insufficient", 3)),
        ((12, 10, None, "<=", 5.0), ("insufficient", 3)),
    ],
    ids=["no-rows", "below-min", "below-min-beats-empty-side", "n-equals-min", "empty-side", "no-value"],
)
def test_status_token_and_exit_code_follow_the_precedence_table(args, expected):
    assert status_of(*args) == expected


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("<", 9.0, "within"), ("<", 10.0, "breach"), ("<", 11.0, "breach"),
        ("<=", 9.0, "within"), ("<=", 10.0, "within"), ("<=", 11.0, "breach"),
        (">", 9.0, "breach"), (">", 10.0, "breach"), (">", 11.0, "within"),
        (">=", 9.0, "breach"), (">=", 10.0, "within"), (">=", 11.0, "within"),
    ],
)
def test_each_operator_is_within_or_breach_on_each_side_of_the_limit(op, value, expected):
    token, code = status_of(12, 10, value, op, 10.0)
    assert (token, code) == (expected, 0 if expected == "within" else 1)


# --- stream names live in streams.py only ------------------------------------


def _string_constants_outside_docstrings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def test_no_stream_name_is_hardcoded_outside_streams_py():
    scripts = REPO_ROOT / "scripts"
    modules = [scripts / "benefit_eval_cli.py", *sorted((scripts / "lib" / "benefit_eval").glob("*.py"))]
    scanned = [path for path in modules if path.name != "streams.py"]
    assert len(scanned) > 1, scanned
    offenders = [
        f"{path.name}: {text!r}"
        for path in scanned
        for text in _string_constants_outside_docstrings(path)
        for name in (*streams.STREAM_TABLE, streams.SUBAGENT_TRANSCRIPTS, streams.BOUNDARY_EVENTS.name)
        if name in text
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "module",
    sorted(path.stem for path in (REPO_ROOT / "scripts" / "lib" / "benefit_eval").glob("*.py") if path.stem != "__init__"),
)
def test_each_module_imports_in_a_fresh_interpreter_with_only_scripts_lib_on_the_path(module, tmp_path):
    env = {"PYTHONPATH": str(REPO_ROOT / "scripts" / "lib"), "PATH": "/usr/bin:/bin"}
    done = subprocess.run(
        [sys.executable, "-c", f"import benefit_eval.{module}"], env=env, cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr


# --- pre-registration parser -------------------------------------------------


def entry(metric_id: str = "skip-rate", **overrides) -> dict:
    base = {
        "id": metric_id,
        "metric": "Skip rate",
        "instrument": "ledger-skips",
        "identity_class": "id-bearing",
        "baseline": "20.69% theoretical ceiling",
        "keep": ">= 10",
        "tune": "< 10",
        "retire": "< 3",
        "direction": ">=",
        "inclusivity": "inclusive",
        "minimum_n": 10,
        "n_unit": "rows",
        "unit": "percent",
        "null_rule": "below minimum N the metric is NULL",
        "parity_cap": "tune",
        "window": "14 days after the merge",
        "confounds": ["workload mix"],
        "computation": "metrics_ledger.skip_rate",
    }
    return {**base, **overrides}


def prereg_text(entries: list[dict], extra_blocks: str = "") -> str:
    block = json.dumps({"metrics": entries}, indent=2)
    return f"# Pre-registration\n\nProse.\n\n```json prereg\n{block}\n```\n{extra_blocks}"


#: Every column a metric entry must fill, written out so the parser's own list cannot shrink unnoticed.
EXPECTED_COLUMNS = (
    "id", "metric", "instrument", "identity_class", "baseline", "keep", "tune", "retire",
    "direction", "inclusivity", "minimum_n", "n_unit", "unit", "null_rule",
    "parity_cap", "window", "confounds", "computation",
)


def named(column: str, metric_id: str = "skip-rate") -> str:
    """How an error names the entry: by id, or by position when the id cell is the empty one."""
    return "metrics[1]" if column == "id" else metric_id


def write_prereg(tmp_path: Path, entries: list[dict], extra_blocks: str = "") -> Path:
    path = tmp_path / "preregistration.md"
    path.write_text(prereg_text(entries, extra_blocks))
    return path


def test_valid_prereg_parses_thresholds_as_number_with_direction(tmp_path):
    loaded = prereg.load_prereg(write_prereg(tmp_path, [entry()]))
    skip = loaded.get("skip-rate")
    assert (skip.keep, skip.retire) == (prereg.Threshold(">=", 10.0), prereg.Threshold("<", 3.0))
    assert skip.confounds == ("workload mix",)


@pytest.mark.parametrize("column", EXPECTED_COLUMNS)
def test_empty_cell_fails_naming_the_metric_and_column(tmp_path, column):
    empty = [] if column == "confounds" else ""
    path = write_prereg(tmp_path, [entry("a"), entry("skip-rate", **{column: empty})])
    with pytest.raises(streams.InputError) as caught:
        prereg.load_prereg(path)
    message = caught.value.message()
    assert f"metric '{named(column)}' column '{column}' is empty" in message
    assert "Next:" in message and str(path) in message


@pytest.mark.parametrize("column", [c for c in EXPECTED_COLUMNS if c != "confounds"])
def test_whitespace_only_cell_counts_as_empty(tmp_path, column):
    path = write_prereg(tmp_path, [entry("a"), entry("skip-rate", **{column: " \t "})])
    with pytest.raises(streams.InputError, match=rf"metric '{re.escape(named(column))}' column '{column}' is empty"):
        prereg.load_prereg(path)


def test_empty_cell_error_points_at_the_entry_line(tmp_path):
    path = write_prereg(tmp_path, [entry("a"), entry("b", retire="")])
    with pytest.raises(streams.InputError) as caught:
        prereg.load_prereg(path)
    assert path.read_text().splitlines()[caught.value.line - 1].strip() == '"id": "b",'


@pytest.mark.parametrize("column", ["keep", "tune", "retire"])
@pytest.mark.parametrize("bad", ["lots", "450", "== 5", "<= ", "<= five", ">>= 3"])
def test_threshold_that_is_not_a_number_with_a_direction_fails_naming_its_column(tmp_path, column, bad):
    with pytest.raises(streams.InputError, match=f"metric 'skip-rate' column '{column}'"):
        prereg.load_prereg(write_prereg(tmp_path, [entry(**{column: bad})]))


def test_inclusive_operator_is_not_read_as_its_exclusive_prefix():
    assert prereg.parse_threshold("<= 450") == streams.Threshold("<=", 450.0)
    assert prereg.parse_threshold(">= 1.5") == streams.Threshold(">=", 1.5)


def test_unknown_metric_id_raises_key_error(tmp_path):
    loaded = prereg.load_prereg(write_prereg(tmp_path, [entry()]))
    with pytest.raises(KeyError):
        loaded.get("absent")


@pytest.mark.parametrize(
    ("overrides", "column"),
    [
        ({"direction": "=="}, "direction"),
        ({"direction": "<=", "keep": "<= 10", "inclusivity": "exclusive"}, "inclusivity"),
        ({"minimum_n": 0}, "minimum_n"),
        ({"minimum_n": "10"}, "minimum_n"),
        ({"parity_cap": "retire"}, "parity_cap"),
        ({"confounds": [""]}, "confounds"),
        ({"confounds": [" "]}, "confounds"),
        ({"keep": "<= 10"}, "keep"),
        ({"identity_class": "id-less", "id_less_handling": "UNVERIFIED"}, "identity_class"),
        ({"instrument": "cost-metering", "identity_class": "id-bearing"}, "identity_class"),
        ({"identity_class": "sometimes"}, "identity_class"),
        ({"instrument": "ledger-skip"}, "instrument"),
        ({"instrument": 5}, "instrument"),
        ({"instrument": ["ledger-skips"]}, "instrument"),
        ({"instrument": {"a": 1}}, "instrument"),
        ({"id_less_handling": "UNVERIFIED"}, "id_less_handling"),
        ({"ceiling": "high"}, "ceiling"),
    ],
)
def test_inconsistent_cell_fails_naming_the_column(tmp_path, overrides, column):
    with pytest.raises(streams.InputError, match=f"column '{column}'"):
        prereg.load_prereg(write_prereg(tmp_path, [entry(**overrides)]))


@pytest.mark.parametrize("handling", [None, "", "both", "unverified"])
def test_id_less_instrument_needs_exactly_one_known_handling(tmp_path, handling):
    cost = entry("cost", instrument="cost-metering", identity_class="id-less", id_less_handling=handling)
    with pytest.raises(streams.InputError, match="column 'id_less_handling'"):
        prereg.load_prereg(write_prereg(tmp_path, [cost]))


def test_id_less_instrument_with_a_declared_handling_parses(tmp_path):
    cost = entry("cost", instrument="cost-metering", identity_class="id-less", id_less_handling="UNVERIFIED")
    assert prereg.load_prereg(write_prereg(tmp_path, [cost])).get("cost").id_less_handling == "UNVERIFIED"


def test_an_id_less_stream_may_declare_unmeasurable_handling(tmp_path):
    cost = entry("cost", instrument="cost-metering", identity_class="id-less", id_less_handling="unmeasurable")
    assert prereg.load_prereg(write_prereg(tmp_path, [cost])).get("cost").id_less_handling == "unmeasurable"


def test_metric_with_no_instrument_must_be_unmeasurable(tmp_path):
    bad = entry("nothing", instrument="none", identity_class="id-less", id_less_handling="UNVERIFIED")
    with pytest.raises(streams.InputError, match="column 'id_less_handling'"):
        prereg.load_prereg(write_prereg(tmp_path, [bad]))


@pytest.mark.parametrize("blocks", [0, 2])
def test_exactly_one_prereg_block_is_required(tmp_path, blocks):
    block = "```json prereg\n" + json.dumps({"metrics": [entry()]}) + "\n```\n"
    path = tmp_path / "preregistration.md"
    path.write_text("# Doc\n\n" + block * blocks)
    with pytest.raises(streams.InputError, match=f"found {blocks}"):
        prereg.load_prereg(path)


def test_other_fenced_blocks_are_ignored(tmp_path):
    path = write_prereg(tmp_path, [entry()], extra_blocks="\n```bash\necho hi\n```\n")
    assert len(prereg.load_prereg(path).metrics) == 1


def test_invalid_json_in_the_block_reports_the_file_line(tmp_path):
    path = tmp_path / "preregistration.md"
    path.write_text('# Doc\n\n```json prereg\n{"metrics": [\n  oops\n]}\n```\n')
    with pytest.raises(streams.InputError) as caught:
        prereg.load_prereg(path)
    assert caught.value.line == 5


def test_duplicate_metric_id_is_rejected(tmp_path):
    with pytest.raises(streams.InputError, match="appears twice"):
        prereg.load_prereg(write_prereg(tmp_path, [entry(), entry()]))


def test_missing_prereg_file_is_malformed_input(tmp_path):
    with pytest.raises(streams.InputError, match="not found"):
        prereg.load_prereg(tmp_path / "absent.md")


# --- audit CLI ---------------------------------------------------------------


cli = load_cli("benefit_eval_cli")

CLI_ENTRIES = [
    entry("skip-rate"),
    entry("token-delta", instrument="cost-metering", identity_class="id-less", id_less_handling="UNVERIFIED"),
    entry("expand-rate", instrument="none", identity_class="id-less", id_less_handling="unmeasurable"),
]


def run_cli(world: World, tmp_path: Path, capsys, *extra: str, entries=None):
    prereg_path = write_prereg(tmp_path, entries or CLI_ENTRIES)
    code = cli.main(cli_argv("audit", world, prereg_path, *extra))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_audit_cli_prints_literal_status_tokens_and_exits_1_for_a_metric_with_no_instrument(
    world, tmp_path, capsys
):
    world.real_sessions("ledger-skips", 3)
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z"}])
    code, out, _ = run_cli(world, tmp_path, capsys)
    assert code == 1
    assert "ledger-skips: confirmed" in out
    assert "cost-metering: no session ids" in out
    assert "expand-rate: no instrument" in out
    assert "\x1b" not in out


def test_audit_cli_exits_0_when_every_instrument_is_confirmed_or_declared(world, tmp_path, capsys):
    world.real_sessions("ledger-skips", 3)
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z"}])
    code, out, _ = run_cli(world, tmp_path, capsys, entries=CLI_ENTRIES[:2])
    assert code == 0
    assert "findings: 0" in out


def test_audit_cli_reports_unverified_row_count(world, tmp_path, capsys):
    rows = [{"ts": "2026-01-01T00:00:00Z"}] * 4
    rows += [{"ts": "2026-01-01T00:00:00Z", "session_id": "no-transcript"}] * 2
    world.stream("ledger-skips", rows)
    _, out, _ = run_cli(world, tmp_path, capsys, entries=CLI_ENTRIES[:1])
    assert "unverified: 6" in out
    assert "real sessions: 0" in out


def test_audit_cli_reports_skipped_transcripts_without_changing_the_exit_code(world, tmp_path, capsys):
    world.real_sessions("ledger-skips", 3, extra_rows=0)
    clean_code, _, _ = run_cli(world, tmp_path, capsys, entries=CLI_ENTRIES[:1])
    path = world.metrics_file("ledger-skips.jsonl")
    path.write_text(path.read_text() + json.dumps({"ts": "2026-01-01T00:00:00Z", "session_id": "bad"}) + "\n")
    world.session("bad", "not json lines\n")
    code, out, _ = run_cli(world, tmp_path, capsys, entries=CLI_ENTRIES[:1])
    assert "skipped transcripts: 1" in out and "real sessions: 3" in out
    assert code == clean_code


@pytest.mark.parametrize("json_mode", [False, True])
def test_audit_cli_never_prints_a_full_session_id(world, tmp_path, capsys, json_mode):
    world.session(LONG_ID)
    world.stream("ledger-skips", [{"ts": "2026-01-01T00:00:00Z", "session_id": LONG_ID}])
    _, out, err = run_cli(world, tmp_path, capsys, *(["--json"] if json_mode else []), entries=CLI_ENTRIES[:1])
    assert LONG_ID[:8] in out
    assert LONG_ID not in out + err
    assert LONG_ID[:9] not in out


def test_audit_cli_json_emits_instrument_status_records(world, tmp_path, capsys):
    world.real_sessions("ledger-skips", 3)
    code, out, _ = run_cli(world, tmp_path, capsys, "--json", entries=CLI_ENTRIES[:1])
    payload = json.loads(out)
    (status,) = payload["statuses"]
    assert payload["exit_code"] == code == 0
    assert (status["instrument"], status["status"], status["real_sessions"]) == ("ledger-skips", "confirmed", 3)
    assert status["metrics"] == ["skip-rate"]


@pytest.mark.parametrize("content", ["not json\n", '{"ts":"2026-01-01T00:00:00Z"}\n{oops\n'])
def test_audit_cli_unreadable_instrument_exits_2_with_file_line_problem_and_next(
    world, tmp_path, capsys, content
):
    path = world.metrics_file("ledger-skips.jsonl")
    path.write_text(content)
    code, out, err = run_cli(world, tmp_path, capsys, entries=CLI_ENTRIES[:1])
    assert code == 2
    assert out == ""
    assert err.startswith(f"{path}:") and ". Next: " in err


def test_audit_cli_incomplete_prereg_exits_2_naming_metric_and_column(world, tmp_path, capsys):
    code, _, err = run_cli(world, tmp_path, capsys, entries=[entry("skip-rate", retire="")])
    assert code == 2
    assert "metric 'skip-rate' column 'retire' is empty" in err


def test_the_audit_path_loads_no_metric_module(world, tmp_path):
    prereg_path = write_prereg(tmp_path, CLI_ENTRIES[:1])
    driver = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('cli', {str(REPO_ROOT / 'scripts' / 'benefit_eval_cli.py')!r})\n"
        "cli = importlib.util.module_from_spec(spec); sys.modules['cli'] = cli; spec.loader.exec_module(cli)\n"
        f"cli.main({cli_argv('audit', world, prereg_path)!r})\n"
        "print(sorted(m for m in sys.modules if m.startswith('benefit_eval.')))\n"
    )
    done = subprocess.run([sys.executable, "-c", driver], capture_output=True, text=True, cwd=tmp_path, check=False)
    assert (done.stderr, done.returncode) == ("", 0)
    loaded = done.stdout.strip().splitlines()[-1]
    assert loaded == "['benefit_eval.formatting', 'benefit_eval.prereg', 'benefit_eval.streams']", done


def test_audit_cli_without_a_command_exits_2(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main([])
    assert caught.value.code == 2


def test_audit_cli_leaves_every_input_and_the_listing_unchanged(world, tmp_path, capsys):
    world.real_sessions("ledger-skips", 3)
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z"}])
    prereg_path = write_prereg(tmp_path, CLI_ENTRIES)
    before = world.snapshot()
    code = cli.main(cli_argv("audit", world, prereg_path))
    out = capsys.readouterr().out
    assert code == 1  # the one finding: expand-rate has no instrument
    assert all(metric["id"] in out for metric in CLI_ENTRIES)
    assert world.snapshot() == before


# --- the real pre-registration document --------------------------------------

EXPECTED_METRIC_IDS = {
    "skip-rate",
    "findings-parity",
    "abort-yield",
    "test-review-tp-change",
    "test-review-token-delta",
    "expand-rate",
    "report-size-cut",
    "injection-overhead",
    "injection-uptake",
    "guard-divergence",
    "guard-false-positive",
    "contradicted-rate",
    "pbt-mutants-killed",
}


@pytest.fixture(scope="module")
def real():
    return prereg.load_prereg(REAL_PREREG)


def test_real_prereg_has_one_complete_entry_per_required_metric(real):
    assert {m.id for m in real.metrics} == EXPECTED_METRIC_IDS
    assert len(real.metrics) == len(EXPECTED_METRIC_IDS)


@pytest.mark.parametrize("column", EXPECTED_COLUMNS)
def test_blanking_any_cell_of_the_real_prereg_fails_naming_metric_and_column(tmp_path, column):
    text = REAL_PREREG.read_text()
    start, end = prereg_block_span(text)
    document = real_prereg_document()
    victim = "metrics[3]" if column == "id" else document["metrics"][3]["id"]
    document["metrics"][3][column] = [] if column == "confounds" else ""
    path = tmp_path / "preregistration.md"
    path.write_text(text[:start] + json.dumps(document, indent=2) + text[end:])
    with pytest.raises(streams.InputError, match=re.escape(f"metric '{victim}' column '{column}'")):
        prereg.load_prereg(path)


def test_every_real_threshold_is_a_number_with_a_direction_and_consistent_inclusivity(real):
    for m in real.metrics:
        assert streams.INCLUSIVITY[m.direction] == m.inclusivity, m.id
        assert m.keep.op == m.direction, m.id


def test_minimum_n_is_10_except_parity_which_counts_hand_run_diffs(real):
    assert {m.id: m.minimum_n for m in real.metrics if m.minimum_n != 10} == {"findings-parity": 3}


def test_parity_caps_the_verdict_at_tune_for_the_delta_scoping_metrics(real):
    capped = {m.id for m in real.metrics if m.parity_cap == "tune"}
    assert capped == {"skip-rate", "findings-parity"}


def test_skip_rate_carries_the_theoretical_ceiling(real):
    assert real.get("skip-rate").ceiling == 20.69


def test_id_less_instruments_each_pin_one_handling(real):
    handling = {m.instrument: m.id_less_handling for m in real.metrics if m.identity_class == "id-less"}
    assert handling == {"artifact-usage": "UNVERIFIED", "none": "unmeasurable"}


def test_metrics_with_no_instrument_are_the_two_tiered_findings_metrics(real):
    assert {m.id for m in real.metrics if m.instrument == "none"} == {"expand-rate", "report-size-cut"}


def test_computation_cell_matches_the_kind_of_instrument(real):
    for m in real.metrics:
        if m.instrument == "none":
            assert m.computation.startswith("unmeasurable:"), m.id
        elif m.instrument == "manual-input":
            assert m.computation.startswith("manual-input:"), m.id
        else:
            assert m.computation.startswith("metrics_"), m.id


def test_metric_ids_appear_only_inside_the_block(real):
    text = REAL_PREREG.read_text()
    start, end = prereg_block_span(text)
    outside = text[:start] + text[end:]
    # The verdict-order paragraph names the metrics that take no verdict; that list is derived from the
    # baseline cells and checked by test_benefit_baseline_status.py, so it is the one allowed prose mention.
    paragraph = verdict_paragraph(text)
    assert paragraph is not None, "the verdict-order paragraph is missing"
    outside = outside.replace(paragraph, "")
    assert [m.id for m in real.metrics if m.id in outside] == []


def test_prereg_is_not_referenced_from_shipped_plugin_files():
    plugin = REPO_ROOT / "plugins" / "dev-team"
    assert plugin.is_dir()
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in plugin.rglob("*.md")
        if "benefit-eval/preregistration" in path.read_text(errors="replace")
    ]
    assert offenders == []


def test_real_prereg_audit_with_no_data_flags_every_stream_and_the_unmeasurable_metrics(world, real):
    statuses = {s.instrument: s for s in streams.audit(real.metrics, world.sources)}
    assert {name: s.status for name, s in statuses.items()} == {
        "ledger-skips": "gap",
        "checkpoint-aborts": "gap",
        "skill-injection": "gap",
        "subagent-stops": "gap",
        "subagent-transcripts": "gap",
        "artifact-usage": "gap",
        "manual-input": "manual",
        "none": "no instrument",
    }
    assert statuses["none"].metrics == ("expand-rate", "report-size-cut")


def test_real_prereg_audit_with_data_reports_confirmed_manual_no_instrument_and_no_session_ids(world, real):
    for name in ("ledger-skips", "checkpoint-aborts", "skill-injection", "subagent-stops"):
        world.real_sessions(name, 3)
    for i in range(3):
        world.subagent(f"sess{i:04d}-aaaa", "a1", [{"type": "assistant"}])
    (world.home / "artifact-usage.json").write_text('{"source-verification":{"use_count":2}}')
    statuses = streams.audit(real.metrics, world.sources)
    assert {s.instrument: s.status for s in statuses} == {
        "ledger-skips": "confirmed",
        "checkpoint-aborts": "confirmed",
        "skill-injection": "confirmed",
        "subagent-stops": "confirmed",
        "subagent-transcripts": "confirmed",
        "artifact-usage": "no session ids",
        "manual-input": "manual",
        "none": "no instrument",
    }
    assert streams.audit_exit_code(statuses) == 1


def test_real_prereg_audit_reports_every_registered_metric_and_exits_1_while_gaps_remain(world, real, capsys):
    # Exit 1 holds while a metric has no instrument (expand-rate, report-size-cut) or only an id-less one
    # (contradicted-rate); it becomes 0 only when no such metric is left.
    code = cli.main(cli_argv("audit", world, REAL_PREREG, "--json"))
    payload = json.loads(capsys.readouterr().out)
    assert code == payload["exit_code"] == 1
    reported = [metric for status in payload["statuses"] for metric in status["metrics"]]
    assert sorted(reported) == sorted(m.id for m in real.metrics)
