"""Unit tests for hooks/testimprove_phase_scope_guard.py (issue #2094 Slice 2).

Filename note: this test file is still named
`test_test_improve_phase_scope_guard.py` (matching the CLI-name-derived
convention `test_test_improve_phase_state.py` already uses for Slice 1's
`testimprove_phase_state.py`) even though the hook module under test is
`testimprove_phase_scope_guard.py` (no underscore after "test" — see that
module's docstring for why).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
_HOOKS_LIB_DIR = _HOOKS_DIR / "lib"
_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
for _dir in (_HOOKS_DIR, _HOOKS_LIB_DIR, _SCRIPTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import testimprove_phase_scope_guard as guard
from test_improve_resume import build_result  # type: ignore[import-not-found]

_CONTRACT_DOC = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "test-improve"
    / "references"
    / "phase-0-approach-contract.md"
)


# --- Step 2.1: the contract doc pins the literal binding_mode key -------


def test_contract_doc_states_the_binding_mode_key() -> None:
    text = _CONTRACT_DOC.read_text(encoding="utf-8")
    assert f"{guard.BINDING_MODE_KEY}:" in text
    # Fix #17 (test-review): the previous version of this test would still
    # pass if the doc dropped the enumerated legal values — strengthen it to
    # assert all three appear near the key, not just the key name itself.
    key_index = text.index(f"{guard.BINDING_MODE_KEY}:")
    nearby = text[key_index : key_index + 400]
    for token in ("none", "xunit-with-annotations", "bdd-runner"):
        assert token in nearby


def test_contract_docs_example_value_parses_via_the_real_parser() -> None:
    """Integration assertion (plan iteration-2 fix): extract the doc's own
    documented example line and feed it through the hook's real parsing
    function, so the doc and the parser cannot drift apart silently."""
    text = _CONTRACT_DOC.read_text(encoding="utf-8")
    example_line = next(
        line
        for line in text.splitlines()
        if f"{guard.BINDING_MODE_KEY}: xunit-with-annotations" in line
    )
    assert guard._parse_binding_mode(example_line) == "xunit-with-annotations"


# --- Step 2.2: deliberate-failure test (red before Step 2.3/2.4 exist) --


def _make_phase_files(root: Path, *tokens: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for token in tokens:
        (root / f"phase-{token}.md").write_text("done\n", encoding="utf-8")
    return root


def _memory_root(project_dir: Path) -> Path:
    return project_dir / ".claude" / "memory" / "test-improve"


# --- Step 2.3: in-flight candidate enumeration + active-phase resolution --


def _write_phase0(memory_dir: Path, binding_mode: str | None) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    if binding_mode is None:
        return
    (memory_dir / "phase-0.md").write_text(
        f"binding_mode: {binding_mode}\n", encoding="utf-8"
    )


def test_zero_candidates_resolves_none_in_flight(tmp_path) -> None:
    result = guard._resolve(tmp_path)
    assert result.status == "none_in_flight"
    assert result.reason == "no in-flight run found"
    assert result.slug is None
    assert result.phase is None


def test_one_candidate_plain_non_phase3_resolution(tmp_path) -> None:
    """phase-5 complete (no phase-6/7) resolves to active phase '6' — the
    ordinary next-phase case, no Phase-3 correction involved."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5"
    )
    _write_phase0(slug_dir, "none")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.slug == "my-repo"
    assert result.phase == "6"


def test_two_candidates_resolves_ambiguous_with_sorted_slug_names(tmp_path) -> None:
    _make_phase_files(_memory_root(tmp_path) / "zebra-repo", "0")
    _make_phase_files(_memory_root(tmp_path) / "alpha-repo", "0")

    result = guard._resolve(tmp_path)

    assert result.status == "ambiguous"
    assert result.slug is None
    assert result.phase is None
    assert result.reason == "ambiguous: multiple candidates: alpha-repo, zebra-repo"


def test_completed_run_excluded_via_phase9_signal(tmp_path) -> None:
    """A run whose phase-9.md is present is complete — never in-flight,
    regardless of whether a .dev-team-reports report file also exists."""
    _make_phase_files(
        _memory_root(tmp_path) / "my-repo",
        "0", "2", "1", "4", "5", "6", "7", "8", "9",
    )

    result = guard._resolve(tmp_path)

    assert result.status == "none_in_flight"
    assert result.reason == "no in-flight run found"


def test_completed_run_excluded_via_report_glob_secondary_signal(tmp_path) -> None:
    """Defensive secondary exclusion: a completed report on disk excludes a
    slug even before/without phase-9.md alone being asked about here —
    covers the narrow phase-9-landed-but-report-not-yet-written window by
    exercising the report-glob branch directly."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5")
    report_dir = (
        tmp_path / ".dev-team-reports" / "test-improve" / "my-repo"
    )
    report_dir.mkdir(parents=True)
    (report_dir / "report-2026-01-01.md").write_text("done\n", encoding="utf-8")

    result = guard._resolve(tmp_path)

    assert result.status == "none_in_flight"
    assert result.reason == "no in-flight run found"


def test_phase3_active_when_binding_mode_not_none_and_no_gherkin(tmp_path) -> None:
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(slug_dir, "xunit-with-annotations")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.phase == "3"


def test_phase3_skipped_when_binding_mode_is_none(tmp_path) -> None:
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(slug_dir, "none")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.phase == "1"


def test_phase3_already_completed_falls_through_to_phase1(tmp_path) -> None:
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(slug_dir, "bdd-runner")
    (slug_dir / "gherkin.md").write_text("done\n", encoding="utf-8")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.phase == "1"


def test_malformed_or_missing_phase0_on_sole_candidate_fails_open(tmp_path) -> None:
    """phase-2.md exists, but phase-0.md is missing entirely (never
    written)."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "2")

    result = guard._resolve(tmp_path)

    assert result.status == "none_in_flight"
    assert result.reason == "malformed or missing phase-0.md"
    assert result.slug == "my-repo"


def test_unparseable_phase0_on_sole_candidate_fails_open(tmp_path) -> None:
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "2")
    (slug_dir / "phase-0.md").write_text("not a key-value line\n", encoding="utf-8")

    result = guard._resolve(tmp_path)

    assert result.status == "none_in_flight"
    assert result.reason == "malformed or missing phase-0.md"


# --- Step 2.4: wire the resolver into the Read guard (evaluate/main) ----


def _audit_events(tmp_path: Path):
    path = tmp_path / ".claude" / "metrics" / "test-improve-phase-scope.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_reading_the_active_phase_file_is_allowed(tmp_path) -> None:
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-5-improve.md", tmp_path
    )

    assert (code, lines) == (0, [])
    assert _audit_events(tmp_path) == []


def test_completed_phase_read_names_the_active_phase_and_audits_the_block(
    tmp_path,
) -> None:
    """This test also serves as the Step 2.2 deliberate-failure evidence
    (fix #13): this file did not exist before this build, so its first
    version — which exercised the not-yet-implemented `evaluate()` — was
    genuinely red (AttributeError) against a hook module that had no
    `evaluate` function yet. The dedicated
    `test_reading_a_completed_phase_file_is_blocked_when_active_phase_is_5`
    tracer test that captured that same red/green transition was deleted as
    a strict subset of this test (test-smell-review) once this one existed."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-2-baseline.md", tmp_path
    )

    assert code == 2
    body = " ".join(lines)
    assert "[BLOCK]" in lines[0]
    assert "Phase 5" in body
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["block"]
    assert events[0]["file"] == "skills/test-improve/references/phase-2-baseline.md"
    assert events[0]["phase"] == "5"
    assert events[0]["slug"] == "my-repo"


def test_future_phase_read_is_blocked(tmp_path) -> None:
    """Only phase-0.md is done — also demonstrates the --analyze-only
    exemption (fix #3) is narrowly scoped to Phase-1 reads only: a Phase-8
    read in this same window still blocks."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-8-validate.md", tmp_path
    )

    assert code == 2
    assert "Phase 2" in " ".join(lines)
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["block"]


def test_shared_non_phase_reference_file_is_always_allowed(tmp_path) -> None:
    """AC2: a reference file that doesn't match phase-<m>-*.md is a no-op —
    no resolution work, no audit line, no exit-code change — regardless of
    the active phase."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")

    code, lines = guard.evaluate(
        "skills/test-improve/references/review-loop.md", tmp_path
    )

    assert (code, lines) == (0, [])
    assert _audit_events(tmp_path) == []


# --- Fix #7 (security-review): sanitize values interpolated into the -----
# --- printed [BLOCK] message -----------------------------------------------


def test_sanitize_for_message_strips_control_chars_and_truncates() -> None:
    assert guard._sanitize_for_message(None) == ""
    assert guard._sanitize_for_message("") == ""
    assert guard._sanitize_for_message("a\nb\tc") == "a b c"
    long_value = "x" * 500
    sanitized = guard._sanitize_for_message(long_value)
    assert len(sanitized) < len(long_value)
    assert sanitized.startswith("x" * guard._MESSAGE_VALUE_MAX_LEN)


def test_block_message_truncates_an_overlong_file_path(tmp_path) -> None:
    """`file_path` is fully caller-controlled — an absurdly long value must
    not be printed verbatim into the [BLOCK] message."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")
    long_dir = "d" * 500
    overlong_path = (
        f"skills/test-improve/references/{long_dir}/../phase-2-baseline.md"
    )

    code, lines = guard.evaluate(overlong_path, tmp_path)

    assert code == 2
    body = "\n".join(lines)
    assert long_dir not in body
    file_line = next(line for line in lines if line.startswith("File: "))
    assert len(file_line) < len(overlong_path)


def test_phase3_active_read_is_allowed_at_the_hook_level(tmp_path) -> None:
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(slug_dir, "xunit-with-annotations")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-3-derive-gherkin.md", tmp_path
    )

    assert (code, lines) == (0, [])


def test_phase3_read_is_blocked_when_phase3_is_not_active(tmp_path) -> None:
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(slug_dir, "none")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-3-derive-gherkin.md", tmp_path
    )

    assert code == 2
    assert "Phase 1" in " ".join(lines)
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["block"]


def test_ambiguous_multiple_in_flight_runs_fails_open_with_audit(tmp_path) -> None:
    _make_phase_files(_memory_root(tmp_path) / "zebra-repo", "0")
    _make_phase_files(_memory_root(tmp_path) / "alpha-repo", "0")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-2-baseline.md", tmp_path
    )

    assert (code, lines) == (0, [])
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]
    assert events[0]["reason"] == "ambiguous: multiple candidates: alpha-repo, zebra-repo"


def test_no_in_flight_run_fails_open_with_audit(tmp_path) -> None:
    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-2-baseline.md", tmp_path
    )

    assert (code, lines) == (0, [])
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]
    assert events[0]["reason"] == "no in-flight run found"


def test_malformed_phase0_fails_open_with_audit_at_evaluate_level(tmp_path) -> None:
    """Fix #15: the malformed/missing-phase-0.md fail-open path (AC4/AC6)
    was previously only exercised via `_resolve()`/`_resolve_active_phase()`
    directly, never through `evaluate()` — the hook's real boundary.

    Also covers the correctness-review finding that the fail-open `audit()`
    call must not drop `slug` when it's available in `result`: the sole
    in-flight candidate is known ("my-repo") even though its `phase-0.md` is
    malformed/missing, so the audited line's `slug` field must be populated,
    not null."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "2")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-1-analyze.md", tmp_path
    )

    assert (code, lines) == (0, [])
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]
    assert events[0]["reason"] == "malformed or missing phase-0.md"
    assert events[0]["slug"] == "my-repo"


def test_windows_backslash_separated_path_is_recognized(tmp_path) -> None:
    """Fix #16: `evaluate()`'s backslash-to-forward-slash normalization
    (Windows-style separators) has direct test coverage — a backslash path
    to the ACTIVE phase's own reference file is allowed."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")

    code, lines = guard.evaluate(
        "skills\\test-improve\\references\\phase-5-improve.md", tmp_path
    )

    assert (code, lines) == (0, [])


# --- Fix #1 (domain-review): guard and test_improve_resume agree on the ---
# --- Phase-3 window --------------------------------------------------------


def test_guard_and_resume_agree_in_the_phase3_window(tmp_path) -> None:
    """Before this fix, the Phase-3 correction lived only inside the guard
    hook — scripts/test_improve_resume.py's `--from-phase` auto-detect (no
    number) called `resolve_auto` directly and had no Phase-3 awareness, so
    given phase-0.md + phase-2.md and `binding_mode: bdd-runner` with no
    gherkin.md yet, it told the operator to resume at Phase 1 while the
    guard hook (correctly) blocked that very read. Both now call the same
    `resolve_with_phase3_correction` (hooks/lib/testimprove_phase_state.py)
    and must agree."""
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(slug_dir, "bdd-runner")

    guard_result = guard._resolve(tmp_path)
    _resume_code, resume_payload = build_result(slug_dir, explicit=None)

    assert guard_result.status == "ok"
    assert guard_result.phase == "3"
    assert resume_payload["resolved_phase"] == "3"


# --- Fix #2 (domain-review): Phase-6/7 boundary is genuinely undecidable ---


def test_phase6_refactor_allowed_no_phase7_is_ambiguous_fails_open(tmp_path) -> None:
    """Unlike Phase 3 (a clean binding_mode + gherkin.md signal), whether
    Phase 7 will run next is genuinely undecidable from persisted state
    alone when refactor-mode is refactor-allowed and phase-7.md hasn't been
    written yet — the [y/b/q] decision itself is never persisted."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6"
    )
    (slug_dir / "phase-0.md").write_text(
        "refactor-mode: refactor-allowed\n", encoding="utf-8"
    )

    result = guard._resolve(tmp_path)

    assert result.status == "none_in_flight"
    assert result.reason == guard.REASON_PHASE_6_7_AMBIGUOUS


def test_phase6_refactor_allowed_read_of_phase7_reference_is_allowed(tmp_path) -> None:
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6"
    )
    (slug_dir / "phase-0.md").write_text(
        "refactor-mode: refactor-allowed\n", encoding="utf-8"
    )

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-7-refactor.md", tmp_path
    )

    assert (code, lines) == (0, [])
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]
    assert events[0]["reason"] == guard.REASON_PHASE_6_7_AMBIGUOUS


def test_phase6_refactor_allowed_with_phase7_done_resolves_normally(tmp_path) -> None:
    """Once phase-7.md exists, the ambiguity is resolved (Phase 7 already
    ran) and ordinary resolution (active phase 8) applies."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6", "7"
    )
    (slug_dir / "phase-0.md").write_text(
        "refactor-mode: refactor-allowed\n", encoding="utf-8"
    )

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.phase == "8"


def test_phase6_no_refactor_mode_resolves_normally_to_phase8(tmp_path) -> None:
    """The ordinary case (refactor-mode: no-refactor, the default) is
    unaffected by the Phase-6/7 ambiguity check."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6"
    )
    (slug_dir / "phase-0.md").write_text(
        "refactor-mode: no-refactor\n", encoding="utf-8"
    )

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.phase == "8"


# --- Fix #3 (domain-review): --analyze-only runs are invisible to the -----
# --- phase model -------------------------------------------------------


def test_analyze_only_phase1_read_allowed_when_only_phase0_done(tmp_path) -> None:
    """--analyze-only runs Phase 1 directly with only phase-0.md persisted —
    a state nothing distinguishes from the common case's ordinary "resume at
    Phase 2" state. A Phase-1 read must not be blocked here."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-1-analyze.md", tmp_path
    )

    assert (code, lines) == (0, [])
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]
    assert events[0]["reason"] == guard.REASON_ANALYZE_ONLY_AMBIGUOUS


def test_phase2_read_allowed_when_only_phase0_done(tmp_path) -> None:
    """Phase 2 (Baseline) is the genuinely active phase in this state for
    the common (non---analyze-only) case, so it is allowed via the ordinary
    equality check, not the --analyze-only exemption."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-2-baseline.md", tmp_path
    )

    assert (code, lines) == (0, [])
    assert _audit_events(tmp_path) == []


# --- Fix #4 (domain-review): unvalidated binding_mode value must not ------
# --- fail closed -----------------------------------------------------------


def test_invalid_binding_mode_value_fails_open_not_confident_phase3(tmp_path) -> None:
    """A truncated/garbled binding_mode value (e.g. `binding_mode: x`) must
    not be treated as "some non-none mode" and confidently force Phase 3
    active — it is treated the same as a missing/unparseable phase-0.md."""
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(slug_dir, "x")

    result = guard._resolve(tmp_path)

    assert result.status == "none_in_flight"
    assert result.reason == "malformed or missing phase-0.md"


# --- Fix #5 (domain-review): phase-0-approach-contract.md is shared, -------
# --- cross-phase content -----------------------------------------------


def test_phase0_approach_contract_doc_always_allowed(tmp_path) -> None:
    """phase-0-approach-contract.md matches the phase-<m>-*.md name pattern
    (phase '0') but hosts shared, cross-phase content (--from-phase /
    --analyze-only semantics, the Phase-6 prompt reference) — it must be
    readable regardless of the active phase, like review-loop.md (AC2)."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-0-approach-contract.md", tmp_path
    )

    assert (code, lines) == (0, [])
    assert _audit_events(tmp_path) == []


# --- Fix #6 (security-review): path-matching bypass -----------------------


def test_unrelated_file_elsewhere_on_disk_is_not_matched(tmp_path) -> None:
    """A file elsewhere on disk sharing the `phase-<m>-*.md` basename
    pattern under an unrelated `references/` directory must never be
    matched — the previous unanchored substring regex matched ANY
    `references/phase-<m>-*.md` suffix, not just this plugin's own
    skills/test-improve/references/."""
    unrelated = tmp_path / "some" / "other-skill" / "references" / "phase-2-fake.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("not a test-improve reference file\n", encoding="utf-8")

    code, lines = guard.evaluate(str(unrelated), tmp_path)

    assert (code, lines) == (0, [])
    assert _audit_events(tmp_path) == []




@pytest.mark.parametrize(
    "bypass_path",
    [
        "skills/test-improve/references//phase-2-baseline.md",
        "skills/test-improve/references/../references/phase-2-baseline.md",
        "skills/test-improve/REFERENCES/Phase-2-Baseline.MD",
    ],
    ids=["double-separator", "parent-traversal", "case-variant"],
)
def test_phase_reference_bypass_variants_still_match_and_block(
    tmp_path, bypass_path
) -> None:
    """A `//`, `/../`, or case-variant path to the SAME real phase-2
    reference file must still be recognized and blocked when it isn't the
    active phase — the previous unanchored substring regex could be
    defeated by any of these without changing which physical file is
    actually read (they all resolve to the same file)."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")

    code, lines = guard.evaluate(bypass_path, tmp_path)

    assert code == 2
    assert "Phase 5" in " ".join(lines)


def test_non_matching_path_is_a_complete_no_op(tmp_path) -> None:
    code, lines = guard.evaluate("plugins/dev-team/SKILL.md", tmp_path)
    assert (code, lines) == (0, [])
    assert _audit_events(tmp_path) == []


def test_empty_file_path_passes_silently(tmp_path) -> None:
    assert guard.evaluate("", tmp_path) == (0, [])


# --- Fix #3 (correctness-review + arch-review): project_dir() is resolved --
# --- lazily, only after a phase-reference match is confirmed ---------------


def test_project_dir_not_resolved_when_file_path_does_not_match(
    tmp_path, monkeypatch
) -> None:
    """This hook is registered on `PreToolUse:Read` — the highest-frequency
    tool call in a session — and the overwhelming majority of Reads don't
    match `_PHASE_REF_BASENAME_RE`. `_project_dir()` shells out to `git
    rev-parse --show-toplevel`; that cost must not be paid for a Read that
    the hook is about to no-op on anyway."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard,
        "read_stdin_json",
        lambda: {"tool_input": {"file_path": "plugins/dev-team/SKILL.md"}},
    )
    with mock.patch.object(guard, "_project_dir") as mock_project_dir:
        assert guard.main() == 0
    mock_project_dir.assert_not_called()


def test_project_dir_is_resolved_when_file_path_matches(tmp_path, monkeypatch) -> None:
    """Companion to the above: a matching path DOES need `project_dir` to
    resolve the active phase, so `_project_dir()` must still be called in
    that case."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard,
        "read_stdin_json",
        lambda: {
            "tool_input": {
                "file_path": "skills/test-improve/references/phase-2-baseline.md"
            }
        },
    )
    with mock.patch.object(guard, "_project_dir", return_value=tmp_path) as mock_pd:
        guard.main()
    mock_pd.assert_called_once()


def test_main_fails_open_on_internal_error(tmp_path, monkeypatch, capsys) -> None:
    """A crash inside the guard never blocks the tool call (AC4)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard, "read_stdin_json", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]
    assert "boom" in events[0]["reason"]


def test_main_blocks_via_stdin_payload(tmp_path, monkeypatch, capsys) -> None:
    """Fix #1 (correctness-review + arch-review): exit-2 block messages must
    dual-write to stderr in addition to stdout (docs/python-hook-contract.md
    "Exception — exit-2 (block) messages" rule) — some Claude Code
    hook-error wrappers surface only stderr on a nonzero hook exit, so a
    stdout-only block message can go completely unseen there."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard,
        "read_stdin_json",
        lambda: {
            "tool_input": {
                "file_path": "skills/test-improve/references/phase-2-baseline.md"
            }
        },
    )
    assert guard.main() == 2
    captured = capsys.readouterr()
    assert "[BLOCK]" in captured.out
    assert "[BLOCK]" in captured.err
    assert captured.out == captured.err
