"""Instrument audit and shared reader for the benefit evaluation.

Covers scripts/lib/benefit_eval/streams.py (reader, real-session filter,
window helpers, audit) and prereg.py (pre-registration parser), plus the
audit CLI in scripts/benefit_eval.py.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from benefit_eval import prereg, streams

LONG_ID = "0123456789abcdef-0123-4567-89ab-cdef01234567"


class World:
    """A project root, a home metrics dir and a transcript tree under tmp_path."""

    def __init__(self, tmp_path: Path):
        self.project = tmp_path / "project"
        self.home = tmp_path / "home-metrics"
        self.projects = tmp_path / "projects"
        for directory in (self.project / ".claude" / "metrics", self.home, self.projects / "proj-a"):
            directory.mkdir(parents=True)
        self.sources = streams.Sources((self.project,), self.home, self.projects)

    def metrics_file(self, name: str) -> Path:
        return self.project / ".claude" / "metrics" / name

    def transcript(self, session_id: str, content: str = '{"type":"user"}\n') -> None:
        (self.projects / "proj-a" / f"{session_id}.jsonl").write_text(content)

    def stream(self, name: str, rows: list[dict]) -> Path:
        path = self.metrics_file(f"{name}.jsonl")
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def real_sessions(self, name: str, count: int, extra_rows: int = 10) -> None:
        """One row per session, plus extra rows from the first session."""
        ids = [f"sess{i:04d}-aaaa" for i in range(count)]
        rows = [{"ts": "2026-01-01T00:00:00Z", "session_id": sid} for sid in ids]
        if ids:
            rows += [{"ts": "2026-01-01T00:00:01Z", "session_id": ids[0]}] * extra_rows
        for sid in ids:
            self.transcript(sid)
        self.stream(name, rows)

    def snapshot(self) -> dict[str, bytes | None]:
        root = self.project.parent
        return {
            str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))
        }


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
    world.transcript("bad-transcript", "this is not json\n")
    result = audit_one(world)
    assert (result.skipped_transcripts, result.real_sessions) == (1, 3)
    assert result.status == baseline.status


def test_subagent_transcript_does_not_make_a_session_real(world):
    sub = world.projects / "proj-a" / "sess0000-aaaa" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.jsonl").write_text('{"type":"user"}\n')
    world.stream("ledger-skips", [{"ts": "2026-01-01T00:00:00Z", "session_id": "agent-abc"}])
    assert audit_one(world).real_sessions == 0


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


def test_every_instrument_log_stream_is_id_bearing_in_the_table():
    from instrument_log import STREAMS

    for name in STREAMS:
        assert streams.STREAM_TABLE[name].identity_class == streams.ID_BEARING


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


def test_json_file_that_is_not_an_object_is_malformed(world):
    (world.home / "artifact-usage.json").write_text("[1, 2]")
    with pytest.raises(streams.InputError, match=r"artifact-usage\.json:0: file is not a JSON object"):
        audit_one(world, "artifact-usage")


# --- session ids -------------------------------------------------------------


def test_listed_session_ids_are_truncated_to_eight_characters(world):
    world.transcript(LONG_ID)
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
    streams.audit([metric("ledger-skips"), metric("cost-metering"), metric("artifact-usage")], world.sources)
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


def test_row_with_a_bad_timestamp_is_malformed_input_naming_its_line():
    with pytest.raises(streams.InputError) as caught:
        streams.rows_in_window(_rows("garbage"), "ts")
    assert caught.value.line == 1


# --- exit-code table ---------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "token", "code"),
    [
        ({"n": 0, "min_n": 10, "value": None, "side_empty": True}, "no rows in window", 3),
        ({"n": 4, "min_n": 10, "value": 1.0}, "NULL (N=4)", 3),
        ({"n": 12, "min_n": 10, "value": 1.0, "side_empty": True}, "insufficient", 3),
        ({"n": 12, "min_n": 10, "value": 450.0, "op": "<=", "limit": 450.0}, "within", 0),
        ({"n": 12, "min_n": 10, "value": 450.0, "op": "<", "limit": 450.0}, "breach", 1),
        ({"n": 12, "min_n": 10, "value": 10.0, "op": ">=", "limit": 10.0}, "within", 0),
        ({"n": 12, "min_n": 10, "value": 10.0, "op": ">", "limit": 10.0}, "breach", 1),
    ],
)
def test_status_token_and_exit_code_follow_the_precedence_table(kwargs, token, code):
    kwargs.setdefault("op", "<=")
    kwargs.setdefault("limit", 0.0)
    outcome = streams.evaluate_status(**kwargs)
    assert (outcome.token, outcome.exit_code) == (token, code)


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
    modules = [scripts / "benefit_eval.py", *sorted((scripts / "lib" / "benefit_eval").glob("*.py"))]
    offenders = [
        f"{path.name}: {text!r}"
        for path in modules
        if path.exists() and path.name != "streams.py"
        for text in _string_constants_outside_docstrings(path)
        for name in streams.STREAM_TABLE
        if name in text
    ]
    assert offenders == []


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


def write_prereg(tmp_path: Path, entries: list[dict], extra_blocks: str = "") -> Path:
    path = tmp_path / "preregistration.md"
    path.write_text(prereg_text(entries, extra_blocks))
    return path


def test_valid_prereg_parses_thresholds_as_number_with_direction(tmp_path):
    loaded = prereg.load_prereg(write_prereg(tmp_path, [entry()]))
    skip = loaded.get("skip-rate")
    assert (skip.keep, skip.retire) == (prereg.Threshold(">=", 10.0), prereg.Threshold("<", 3.0))
    assert skip.confounds == ("workload mix",)


@pytest.mark.parametrize("column", [c for c in prereg.REQUIRED_COLUMNS if c != "id"])
def test_empty_cell_fails_naming_the_metric_and_column(tmp_path, column):
    empty = [] if column == "confounds" else ""
    path = write_prereg(tmp_path, [entry("a"), entry("skip-rate", **{column: empty})])
    with pytest.raises(streams.InputError) as caught:
        prereg.load_prereg(path)
    message = caught.value.message()
    assert f"metric 'skip-rate' column '{column}' is empty" in message
    assert "Next:" in message and str(path) in message


def test_empty_cell_error_points_at_the_entry_line(tmp_path):
    path = write_prereg(tmp_path, [entry("a"), entry("b", retire="")])
    with pytest.raises(streams.InputError) as caught:
        prereg.load_prereg(path)
    assert path.read_text().splitlines()[caught.value.line - 1].strip() == '"id": "b",'


@pytest.mark.parametrize("bad", ["lots", "450", "== 5", "<= ", "<= five", ">>= 3"])
def test_threshold_that_is_not_a_number_with_a_direction_fails_naming_retire(tmp_path, bad):
    with pytest.raises(streams.InputError, match="metric 'skip-rate' column 'retire'"):
        prereg.load_prereg(write_prereg(tmp_path, [entry(retire=bad)]))


@pytest.mark.parametrize(
    ("overrides", "column"),
    [
        ({"direction": "=="}, "direction"),
        ({"direction": "<=", "inclusivity": "exclusive"}, "inclusivity"),
        ({"minimum_n": 0}, "minimum_n"),
        ({"minimum_n": "10"}, "minimum_n"),
        ({"parity_cap": "retire"}, "parity_cap"),
        ({"confounds": [""]}, "confounds"),
        ({"identity_class": "id-less", "id_less_handling": "UNVERIFIED"}, "identity_class"),
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


def _load_cli():
    spec = importlib.util.spec_from_file_location("benefit_eval_cli", REPO_ROOT / "scripts" / "benefit_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()

CLI_ENTRIES = [
    entry("skip-rate"),
    entry("token-delta", instrument="cost-metering", identity_class="id-less", id_less_handling="UNVERIFIED"),
    entry("expand-rate", instrument="none", identity_class="id-less", id_less_handling="unmeasurable"),
]


def run_cli(world: World, tmp_path: Path, capsys, *extra: str, entries=None):
    prereg_path = write_prereg(tmp_path, entries or CLI_ENTRIES)
    code = cli.main(
        [
            "audit",
            "--prereg", str(prereg_path),
            "--project-root", str(world.project),
            "--home-metrics", str(world.home),
            "--projects-root", str(world.projects),
            *extra,
        ]
    )
    out = capsys.readouterr()
    return code, out.out, out.err


def test_audit_cli_prints_literal_status_tokens_and_exits_1_on_a_gap(world, tmp_path, capsys):
    world.real_sessions("ledger-skips", 3)
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z"}])
    code, out, _ = run_cli(world, tmp_path, capsys)
    assert code == 1
    assert "ledger-skips: confirmed" in out
    assert "cost-metering: no session ids" in out
    assert "none: no instrument" in out
    assert "metrics: expand-rate" in out
    assert "\x1b" not in out


def test_audit_cli_exits_0_when_every_instrument_is_confirmed_or_declared(world, tmp_path, capsys):
    world.real_sessions("ledger-skips", 3)
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z"}])
    code, out, _ = run_cli(world, tmp_path, capsys, entries=CLI_ENTRIES[:2])
    assert (code, "findings: 0" in out) == (0, True)


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
    world.transcript("bad", "not json lines\n")
    code, out, _ = run_cli(world, tmp_path, capsys, entries=CLI_ENTRIES[:1])
    assert "skipped transcripts: 1" in out and "real sessions: 3" in out
    assert code == clean_code


@pytest.mark.parametrize("json_mode", [False, True])
def test_audit_cli_never_prints_a_full_session_id(world, tmp_path, capsys, json_mode):
    world.transcript(LONG_ID)
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


def test_audit_cli_without_a_command_exits_2(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main([])
    assert caught.value.code == 2


def test_audit_cli_leaves_every_input_and_the_listing_unchanged(world, tmp_path, capsys):
    world.real_sessions("ledger-skips", 3)
    world.stream("cost-metering", [{"timestamp": "2026-01-01T00:00:00Z"}])
    prereg_path = write_prereg(tmp_path, CLI_ENTRIES)
    before = world.snapshot()
    cli.main(
        [
            "audit",
            "--prereg", str(prereg_path),
            "--project-root", str(world.project),
            "--home-metrics", str(world.home),
            "--projects-root", str(world.projects),
        ]
    )
    capsys.readouterr()
    assert world.snapshot() == before
