"""Tests for hooks/acceptance_examination_recorder.py (#2270, Step 3.2).

Runs the hook as a subprocess against a pinned temp git repository and
transcript JSONL fixtures (`examiner_fixtures.py`), then reads back the record
under `.claude/memory/` and the events under `.claude/metrics/`. One test (or
parametrized outline) per scenario in the plan's `Feature: Examiner transcript
recorder`.
"""

from __future__ import annotations

import io
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parents[2]
_HOOK_PY = _PLUGIN_DIR / "hooks" / "acceptance_examination_recorder.py"
for _p in (
    _PLUGIN_DIR / "hooks",
    _PLUGIN_DIR / "hooks" / "lib",
    _PLUGIN_DIR / "tests" / "lib",
    Path(__file__).parent,
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
# examination_gate lives in scripts/lib; appended so it cannot shadow a hooks/lib module.
_SCRIPTS_LIB_DIR = _PLUGIN_DIR / "scripts" / "lib"
if str(_SCRIPTS_LIB_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_LIB_DIR))

import acceptance_examination_recorder as recorder  # type: ignore[import-not-found]
import examination_gate  # type: ignore[import-not-found]
import examination_store as store  # type: ignore[import-not-found]
from examination_inputs import (  # type: ignore[import-not-found]
    inputs_digest,
    plan_examination_inputs,
)
from examination_repo import (  # type: ignore[import-not-found]
    CRITERION_1,
    CRITERION_2,
    PLAN_ID,
    PLAN_TEXT,
    commit_file,
    git_env,
    init_repo,
    make_repo,
    row,
)
from examination_store import Binding  # type: ignore[import-not-found]
from examination_verdict import build_record  # type: ignore[import-not-found]
from examiner_fixtures import (  # type: ignore[import-not-found]
    AGENT_ID,
    SESSION_ID,
    bash_call_rows,
    dispatch_row,
    handback_rows,
    stop_payload,
    write_transcript,
)
from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_EVENTS_REL = Path(".claude") / "metrics" / "boundary-events.jsonl"
_RECORD_GLOB = ".claude/memory/acceptance-examination-*"
_RAN = "pytest -q"
_FEATURE_READ = "cat features/login.feature"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _met_result() -> dict:
    return {"criteria": [row("AC1", command=_RAN), row("AC2", command=_RAN)]}


def _examiner_rows(
    *,
    marker: str | None = PLAN_ID,
    commands: tuple[str, ...] = (_RAN, _FEATURE_READ),
    handback: str | None = None,
) -> list[dict]:
    """A complete examiner transcript; `handback` defaults to a clean `met`."""
    rows = [dispatch_row(marker)]
    for command in commands:
        rows += bash_call_rows(command)
    text = json.dumps(_met_result()) if handback is None else handback
    return rows + handback_rows(text)


def _run_hook(raw_stdin: bytes, home: Path) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env.update(
        {
            key: value
            for key, value in hermetic_git_env(home).items()
            if key.startswith("GIT_")
        }
    )
    env["GIT_CEILING_DIRECTORIES"] = str(home.parent)
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=raw_stdin,
        env=env,
        capture_output=True,
        timeout=30,
        check=False,
    )


def _payload_for(repo: Path, rows: list[dict], *, cwd: Path | None = None) -> bytes:
    transcript = write_transcript(repo.parent, rows)
    return json.dumps(stop_payload(cwd or repo, transcript)).encode()


def _stop(repo: Path, rows: list[dict], *, cwd: Path | None = None) -> None:
    """Write `rows` as the examiner's transcript, stop the subagent, and assert
    the hook's silent exit-zero contract."""
    _stop_raw(repo, _payload_for(repo, rows, cwd=cwd))


def _stop_raw(repo: Path, raw_stdin: bytes) -> None:
    result = _run_hook(raw_stdin, repo.parent)
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def _record_files(repo: Path) -> list[Path]:
    return sorted(repo.glob(_RECORD_GLOB))


def _record(repo: Path) -> dict:
    return store.read_record(store.record_path(repo, PLAN_ID))


def _events(repo: Path) -> list[dict]:
    path = repo / _EVENTS_REL
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The pinned repo; in-process git calls (binding, gate) run hermetically."""
    for key, value in git_env(tmp_path).items():
        monkeypatch.setenv(key, value)
    return make_repo(tmp_path)


# ---------------------------------------------------------------------------
# Scenario: A clean examiner transcript writes a "met" record
# ---------------------------------------------------------------------------


def test_clean_transcript_writes_met_record_bound_to_branch_and_inputs(
    repo: Path,
) -> None:
    _stop(repo, _examiner_rows())

    record = _record(repo)
    assert record["overall"] == "met"
    assert record["plan"] == PLAN_ID
    assert record["agent_id"] == AGENT_ID
    assert record["binding_hash"] == store.current_binding(repo, PLAN_ID)
    assert record["inputs_digest"] == inputs_digest(plan_examination_inputs(PLAN_TEXT))
    assert record["problems"] == []
    assert record["audit_findings"] == []
    assert _events(repo) == []


def test_hook_written_met_record_passes_the_gate(repo: Path) -> None:
    _stop(repo, _examiner_rows())

    assert examination_gate.load_and_check(repo / PLAN_ID) == []


# ---------------------------------------------------------------------------
# Scenario: Filter and feature reads are not forbidden
# ---------------------------------------------------------------------------


def test_filter_and_feature_reads_leave_record_met_and_emit_no_event(
    repo: Path,
) -> None:
    commands = (_RAN, _FEATURE_READ, "pytest -q | grep v1.2", "cat features/x.feature")
    _stop(repo, _examiner_rows(commands=commands))

    assert _record(repo)["overall"] == "met"
    assert _events(repo) == []


# ---------------------------------------------------------------------------
# Scenario: A non-examiner transcript is ignored
# ---------------------------------------------------------------------------


def test_non_examiner_transcript_writes_no_record_and_no_event(repo: Path) -> None:
    rows = [dispatch_row(PLAN_ID)] + bash_call_rows(
        "cat src/app.py", attribution_agent="dev-team:software-engineer"
    )
    _stop(repo, rows)

    assert _record_files(repo) == []
    assert _events(repo) == []


# ---------------------------------------------------------------------------
# Scenario: A missing plan marker writes no record
# ---------------------------------------------------------------------------


def test_marker_only_in_later_turn_writes_no_record_and_one_event(
    repo: Path,
) -> None:
    rows = [dispatch_row(None), dispatch_row(PLAN_ID)] + _examiner_rows()[1:]
    _stop(repo, rows)

    assert _record_files(repo) == []
    events = _events(repo)
    assert [e["matched_rule"] for e in events] == ["missing-plan-marker"]
    assert events[0]["hook"] == "acceptance_examination_recorder"
    assert events[0]["decision"] == "record"
    assert events[0]["session_id"] == SESSION_ID


# ---------------------------------------------------------------------------
# Scenario: A forbidden read taints the record
# ---------------------------------------------------------------------------

_FORBIDDEN_READS = ("cat src/app.py", "head -3 src/b.py")


def test_forbidden_reads_taint_record_and_emit_one_event_without_path_text(
    repo: Path,
) -> None:
    commands = (_RAN, _FEATURE_READ, *_FORBIDDEN_READS)
    _stop(repo, _examiner_rows(commands=commands))

    record = _record(repo)
    assert record["overall"] == "tainted"
    assert [
        (f["kind"], f["target"], f["command"]) for f in record["audit_findings"]
    ] == [
        ("read", "src/app.py", "cat src/app.py"),
        ("read", "src/b.py", "head -3 src/b.py"),
    ]
    events = _events(repo)
    assert [e["matched_rule"] for e in events] == ["examiner-forbidden-read"]
    serialized = json.dumps(events[0])
    for leaked in ("src/app.py", "src/b.py", "cat ", "head "):
        assert leaked not in serialized


# ---------------------------------------------------------------------------
# Scenario Outline: A state-changing command taints the record
# ---------------------------------------------------------------------------


_RECORD_REL = store.record_path(Path("/"), PLAN_ID).relative_to("/").as_posix()


@pytest.mark.parametrize(
    ("command", "kind", "target"),
    [
        (f"echo '{{}}' > {_RECORD_REL}", "write", _RECORD_REL),
        ("git commit -am wip", "git", "commit"),
        ("sed -i s/a/b/ src/app.py", "write", "src/app.py"),
    ],
)
def test_state_changing_command_taints_record(
    repo: Path, command: str, kind: str, target: str
) -> None:
    _stop(repo, _examiner_rows(commands=(_RAN, command)))

    record = _record(repo)
    assert record["overall"] == "tainted"
    assert [
        (f["kind"], f["target"], f["command"]) for f in record["audit_findings"]
    ] == [(kind, target, command)]


# ---------------------------------------------------------------------------
# Scenario: A handback with a missing row is recorded as indeterminate
# ---------------------------------------------------------------------------


def test_handback_missing_a_row_is_indeterminate_naming_the_missing_id(
    repo: Path,
) -> None:
    handback = json.dumps({"criteria": [row("AC1", command=_RAN)]})
    _stop(repo, _examiner_rows(handback=handback))

    record = _record(repo)
    assert record["overall"] == "indeterminate"
    assert "missing AC2" in record["problems"]


# ---------------------------------------------------------------------------
# Scenario Outline: A malformed handback is recorded as indeterminate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("handback", "problem"),
    [
        pytest.param("All criteria look fine to me.", "unparseable-result", id="prose"),
        pytest.param(
            json.dumps({"summary": "done"}), "invalid-result-shape", id="no-criteria"
        ),
        pytest.param(
            json.dumps({"criteria": ["AC1 met", "AC2 met"]}),
            "invalid-result-shape",
            id="string-rows",
        ),
    ],
)
def test_malformed_handback_is_indeterminate_and_still_recorded(
    repo: Path, handback: str, problem: str
) -> None:
    _stop(repo, _examiner_rows(handback=handback))

    record = _record(repo)
    assert record["overall"] == "indeterminate"
    assert problem in record["problems"]
    assert record["criteria"] == []


def test_prose_handback_for_a_plan_without_criteria_keeps_the_no_criteria_problem(
    repo: Path,
) -> None:
    no_criteria_plan = PLAN_TEXT.replace(
        f"- [ ] {CRITERION_1}\n- [ ] {CRITERION_2}\n", ""
    )
    commit_file(repo, PLAN_ID, no_criteria_plan, "docs: drop the criteria")
    _stop(repo, _examiner_rows(handback="All criteria look fine to me."))

    record = _record(repo)
    assert record["overall"] == "indeterminate"
    assert record["problems"] == ["unparseable-result", "no-acceptance-criteria"]


# ---------------------------------------------------------------------------
# Scenario: The examiner's cwd is resolved before the read audit
# ---------------------------------------------------------------------------


def test_forbidden_read_is_found_when_the_payload_cwd_is_a_symlink_to_the_repo(
    repo: Path,
) -> None:
    link = repo.parent / "link"
    link.symlink_to(repo, target_is_directory=True)

    _stop(repo, _examiner_rows(commands=(_RAN, "cat src/app.py")), cwd=link)

    record = _record(repo)
    assert record["overall"] == "tainted"
    assert [(f["kind"], f["target"]) for f in record["audit_findings"]] == [
        ("read", "src/app.py")
    ]


# ---------------------------------------------------------------------------
# Scenario Outline: An unavailable binding is recorded as indeterminate
# ---------------------------------------------------------------------------


def _repo_without_base(tmp_path: Path) -> Path:
    """The plan and a source file on a lone `work` branch: no base ref resolves."""
    root = tmp_path / "repo"
    init_repo(root, "work")
    commit_file(root, PLAN_ID, PLAN_TEXT, "docs: add plan")
    commit_file(root, "docs/feature.md", "feature\n", "feat: add feature")
    return root


@pytest.mark.parametrize("state", ["base-unresolvable", "empty-diff"])
def test_unavailable_binding_is_indeterminate_with_binding_problem(
    tmp_path: Path, state: str
) -> None:
    root = (
        _repo_without_base(tmp_path)
        if state == "base-unresolvable"
        else make_repo(tmp_path, with_source=False)
    )
    _stop(root, _examiner_rows())

    record = _record(root)
    assert record["overall"] == "indeterminate"
    assert "binding-hash-unavailable" in record["problems"]
    assert record["binding_hash"] == state


# ---------------------------------------------------------------------------
# Scenario: A second examination replaces the first record
# ---------------------------------------------------------------------------


def test_second_examination_replaces_the_first_record(repo: Path) -> None:
    earlier = build_record(
        PLAN_ID,
        [row("AC1", "not-met"), row("AC2")],
        [],
        [],
        Binding("a" * 64, "d" * 64),
        "agent-earlier",
    )
    store.write_record(store.record_path(repo, PLAN_ID), earlier)
    assert _record(repo)["overall"] == "not-met"

    _stop(repo, _examiner_rows())

    assert _record(repo)["overall"] == "met"
    assert [p.name for p in _record_files(repo) if p.suffix == ".json"] == [
        store.record_path(repo, PLAN_ID).name
    ]


# ---------------------------------------------------------------------------
# Scenario Outline: The recorder never blocks on infrastructure failure
# ---------------------------------------------------------------------------


def _fault_missing_transcript(repo: Path) -> bytes:
    payload = stop_payload(repo, repo.parent / "missing" / "session.jsonl")
    return json.dumps(payload).encode()


def _fault_not_json(repo: Path) -> bytes:
    return b"this is { not json"


def _fault_memory_dir_not_writable(repo: Path) -> bytes:
    memory = repo / ".claude" / "memory"
    memory.mkdir(parents=True)
    memory.chmod(0o500)
    return _payload_for(repo, _examiner_rows())


def _fault_memory_dir_is_a_file(repo: Path) -> bytes:
    (repo / ".claude").mkdir()
    (repo / ".claude" / "memory").write_text("not a directory", encoding="utf-8")
    return _payload_for(repo, _examiner_rows())


def _fault_plan_missing(repo: Path) -> bytes:
    return _payload_for(repo, _examiner_rows(marker="plans/missing.md"))


def _fault_marker_has_parent_segment(repo: Path) -> bytes:
    return _payload_for(repo, _examiner_rows(marker="../repo/plans/x.md"))


def _fault_cwd_not_a_repository(repo: Path) -> bytes:
    elsewhere = repo.parent / "elsewhere"
    elsewhere.mkdir()
    return _payload_for(repo, _examiner_rows(), cwd=elsewhere)


_SKIP_AS_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses directory permission bits",
)

_FAULTS = [
    pytest.param(_fault_missing_transcript, id="transcript-missing"),
    pytest.param(_fault_not_json, id="stdin-not-json"),
    pytest.param(
        _fault_memory_dir_not_writable, id="memory-dir-read-only", marks=_SKIP_AS_ROOT
    ),
    pytest.param(_fault_memory_dir_is_a_file, id="memory-dir-is-a-file"),
    pytest.param(_fault_plan_missing, id="plan-missing"),
    pytest.param(_fault_marker_has_parent_segment, id="marker-has-dotdot"),
    pytest.param(_fault_cwd_not_a_repository, id="cwd-not-a-repo"),
]


@pytest.mark.parametrize("fault", _FAULTS)
def test_infrastructure_fault_exits_zero_silently_and_leaves_no_record_file(
    repo: Path, fault
) -> None:
    raw_stdin = fault(repo)
    try:
        _stop_raw(repo, raw_stdin)
    finally:
        memory = repo / ".claude" / "memory"
        if memory.is_dir():
            memory.chmod(0o700)

    assert _record_files(repo) == []
    assert list(repo.parent.glob("elsewhere/" + _RECORD_GLOB)) == []


def _main_with_stdin(monkeypatch: pytest.MonkeyPatch, raw_stdin: bytes) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw_stdin.decode()))
    return recorder.main()


def test_unexpected_error_in_process_exits_zero_silently(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    calls: list[str] = []

    def explode(payload: dict, cwd: str) -> None:
        calls.append(cwd)
        raise RuntimeError("boom")

    monkeypatch.setattr(recorder, "process", explode)

    assert _main_with_stdin(monkeypatch, _payload_for(repo, _examiner_rows())) == 0
    captured = capsys.readouterr()
    assert calls == [str(repo)]
    assert (captured.out, captured.err) == ("", "")
    assert _record_files(repo) == []


def test_record_write_failure_exits_zero_silently_and_leaves_no_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    attempts: list[Path] = []

    def fail_write(path: Path, record: dict) -> None:
        attempts.append(Path(path))
        raise OSError("disk full")

    monkeypatch.setattr(recorder, "write_record", fail_write)

    assert _main_with_stdin(monkeypatch, _payload_for(repo, _examiner_rows())) == 0
    captured = capsys.readouterr()
    assert attempts == [store.record_path(repo, PLAN_ID)]
    assert (captured.out, captured.err) == ("", "")
    assert _record_files(repo) == []


# ---------------------------------------------------------------------------
# Every matched_rule the hook emits is documented
# ---------------------------------------------------------------------------

_TELEMETRY_SCHEMA = _PLUGIN_DIR / "knowledge" / "telemetry-schema.md"


def _emitted_rules() -> list[str]:
    return [
        value
        for name, value in vars(recorder).items()
        if name.startswith("RULE_") and isinstance(value, str)
    ]


def test_every_matched_rule_the_hook_emits_is_in_the_telemetry_schema() -> None:
    rules = _emitted_rules()
    schema = _TELEMETRY_SCHEMA.read_text(encoding="utf-8")

    assert sorted(rules) == ["examiner-forbidden-read", "missing-plan-marker"]
    assert [rule for rule in rules if f"`{rule}`" not in schema] == []


# ---------------------------------------------------------------------------
# Step 3.3: registration on SubagentStop, after review_verdict_recorder.py
# ---------------------------------------------------------------------------

_SETTINGS_JSON = _PLUGIN_DIR / "settings.json"
_HOOKS_JSON = _PLUGIN_DIR / "hooks" / "hooks.json"
_PRECEDING_HOOK = "review_verdict_recorder.py"


def _subagent_stop_scripts(path: Path) -> list[str]:
    """Basenames of every SubagentStop command in `path`, in order."""
    groups = json.loads(path.read_text(encoding="utf-8"))["hooks"]["SubagentStop"]
    return [
        Path(shlex.split(hook["command"])[-1]).name
        for group in groups
        for hook in group["hooks"]
    ]


def _recorder_offset_from_verdict_recorder(registry: Path) -> int:
    scripts = _subagent_stop_scripts(registry)
    assert scripts.count(_HOOK_PY.name) == 1
    return scripts.index(_HOOK_PY.name) - scripts.index(_PRECEDING_HOOK)


@pytest.mark.parametrize(
    "registry", [_SETTINGS_JSON, _HOOKS_JSON], ids=lambda p: p.name
)
def test_registry_lists_the_recorder_once_right_after_the_verdict_recorder(
    registry: Path,
) -> None:
    assert _recorder_offset_from_verdict_recorder(registry) == 1


def test_both_registries_place_the_recorder_at_the_same_relative_position() -> None:
    assert _recorder_offset_from_verdict_recorder(
        _SETTINGS_JSON
    ) == _recorder_offset_from_verdict_recorder(_HOOKS_JSON)
