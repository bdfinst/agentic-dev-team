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
import os
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


def _write_phase0_text(memory_dir: Path, text: str) -> None:
    """Write `phase-0.md`'s raw text, then back-date its mtime to be no
    newer than any sibling `phase-N.md` file already present. Phase 0
    always executes (and its progress file is always written) FIRST in a
    real `/test-improve` run, so a test fixture that creates placeholder
    phase files via `_make_phase_files` and only afterward overwrites
    `phase-0.md`'s real content must not leave `phase-0.md` looking
    artificially newer than its siblings — `_prune_stale_tokens`'s
    freshness check would otherwise wrongly treat every sibling as a stale
    leftover from a prior run."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    phase0 = memory_dir / "phase-0.md"
    phase0.write_text(text, encoding="utf-8")
    sibling_mtimes = [
        f.stat().st_mtime for f in memory_dir.glob("phase-*.md") if f.name != "phase-0.md"
    ]
    if sibling_mtimes:
        oldest = min(sibling_mtimes) - 1
        os.utime(phase0, (oldest, oldest))


def _write_phase0(memory_dir: Path, binding_mode: str | None) -> None:
    if binding_mode is None:
        memory_dir.mkdir(parents=True, exist_ok=True)
        return
    _write_phase0_text(memory_dir, f"binding_mode: {binding_mode}\n")


def test_zero_candidates_resolves_unresolved(tmp_path) -> None:
    result = guard._resolve(tmp_path)
    assert result.status == "unresolved"
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


def test_stray_dir_without_phase0_does_not_mask_real_candidate_as_ambiguous(
    tmp_path,
) -> None:
    """Review fix (issue #2094 follow-up): `_find_in_flight_slugs` used to
    count ANY subdirectory with at least one phase file as a candidate, never
    requiring phase-0.md -- so a stray/partial leftover directory (no
    phase-0.md, /test-improve always writes it first) coexisting with a real
    in-flight run falsely tripped the ambiguous-multiple-candidates path and
    lost the ability to gate the real run's phase-reference reads."""
    my_repo = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(my_repo, "none")
    _make_phase_files(_memory_root(tmp_path) / "stray-leftover", "5")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.slug == "my-repo"


def test_completed_run_excluded_via_phase9_signal(tmp_path) -> None:
    """A run whose phase-9.md is present is complete — never in-flight,
    regardless of whether a .dev-team-reports report file also exists."""
    _make_phase_files(
        _memory_root(tmp_path) / "my-repo",
        "0", "2", "1", "4", "5", "6", "7", "8", "9",
    )

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
    assert result.reason == "no in-flight run found"


def test_reset_flow_stale_phase9_does_not_mask_the_new_run(tmp_path) -> None:
    """Review fix (issue #2094 follow-up): SKILL.md's own documented "change
    Phase-0 answers" flow deletes ONLY phase-0.md and re-runs from Phase 0,
    deliberately leaving phase-1.md..phase-9.md from the PRIOR run in place.
    Without a freshness check, the leftover phase-9.md alone made
    resolve_with_phase3_correction report `complete=True` for the brand-new
    run, excluding it from candidacy and silently disabling the guard for
    the run's entire lifetime -- the exact reset workflow SKILL.md tells
    operators to use. Only phase files at least as new as phase-0.md's own
    (re)write now count as this run's progress."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo",
        "1", "2", "4", "5", "6", "7", "8", "9",
    )
    an_hour_ago = (slug_dir / "phase-9.md").stat().st_mtime - 3600
    for token in ("1", "2", "4", "5", "6", "7", "8", "9"):
        stale_file = slug_dir / f"phase-{token}.md"
        os.utime(stale_file, (an_hour_ago, an_hour_ago))
    # Deliberately NOT _write_phase0()/_write_phase0_text() here -- those
    # back-date phase-0.md to match real /test-improve chronology (Phase 0
    # always written first), which would defeat this test's premise that
    # phase-0.md was just freshly (re)written AFTER the stale siblings.
    (slug_dir / "phase-0.md").write_text("binding_mode: none\n", encoding="utf-8")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.slug == "my-repo"
    assert result.phase == "2"


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

    assert result.status == "unresolved"
    assert result.reason == "no in-flight run found"


def test_stale_report_from_prior_completed_run_does_not_mask_fresh_run(
    tmp_path,
) -> None:
    """Review fix (issue #2094 follow-up): the report-glob secondary
    exclusion used to fire for ANY report ever written under a slug, with no
    regard for whether it belonged to the CURRENT set of phase files -- so a
    repo that completed /test-improve once permanently masked every later,
    genuinely in-flight run under the same slug. Only a report at least as
    new as the run's newest phase file now counts as evidence of ITS
    completion."""

    report_dir = tmp_path / ".dev-team-reports" / "test-improve" / "my-repo"
    report_dir.mkdir(parents=True)
    stale_report = report_dir / "report-2025-01-01.md"
    stale_report.write_text("old run\n", encoding="utf-8")
    an_hour_ago = stale_report.stat().st_mtime - 3600
    os.utime(stale_report, (an_hour_ago, an_hour_ago))

    my_repo = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(my_repo, "none")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.slug == "my-repo"


def test_report_tied_with_newest_phase_file_does_not_mask_in_flight_run(
    tmp_path,
) -> None:
    """Review fix (issue #2094 follow-up, round 14): the report-vs-phase-
    file freshness comparison used `>=` on second-resolution `st_mtime` —
    the same coarse-mtime-tie hardening round 13 already applied to
    prune_stale_tokens/_gherkin_done_for_this_run, missed here. A report
    whose mtime TIES the newest phase file's must not mask (exclude) a
    genuinely in-flight run — masking on a tie is the "guard silently
    disabled" failure direction this whole issue exists to prevent."""
    my_repo = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2")
    _write_phase0(my_repo, "none")
    report_dir = tmp_path / ".dev-team-reports" / "test-improve" / "my-repo"
    report_dir.mkdir(parents=True)
    report = report_dir / "report-2026-01-01.md"
    report.write_text("done\n", encoding="utf-8")
    newest_phase_ns = max(f.stat().st_mtime_ns for f in my_repo.glob("phase-*.md"))
    os.utime(report, ns=(newest_phase_ns, newest_phase_ns))

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.slug == "my-repo"


def test_phase6_stale_leftover_phase7_from_prior_run_is_still_ambiguous(
    tmp_path,
) -> None:
    """Review fix (issue #2094 follow-up, round 14): the Phase-6/7 check
    used a raw `.exists()` on phase-7.md instead of checking the caller's
    already freshness-pruned `tokens` list. SKILL.md's documented reset
    flow deletes ONLY phase-0.md, leaving phase-1..9.md from a PRIOR run
    in place — a stale leftover phase-7.md from that prior run would
    `.exists()` even though pruning already excluded "7" from `tokens`
    (why `highest == "6"` at all), wrongly resolving this as NOT ambiguous
    and falling through to phase 8 instead of failing open."""
    slug_dir = _memory_root(tmp_path) / "my-repo"
    slug_dir.mkdir(parents=True)
    stale_phase7 = slug_dir / "phase-7.md"
    stale_phase7.write_text("done\n", encoding="utf-8")
    an_hour_ago = stale_phase7.stat().st_mtime - 3600
    os.utime(stale_phase7, (an_hour_ago, an_hour_ago))
    # This run's OWN genuine progress: phase-0.md written first (always the
    # start of a real run) and AFTER the stale phase-7.md leftover, then
    # phase-2/1/4/5/6.md following it -- all this run's own fresh progress.
    (slug_dir / "phase-0.md").write_text(
        "refactor-mode: refactor-allowed\n", encoding="utf-8"
    )
    _make_phase_files(slug_dir, "2", "1", "4", "5", "6")

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
    assert result.reason == guard.REASON_PHASE_6_7_AMBIGUOUS


# --- Review fix: legacy (pre-.claude/-scoped) memory tree migration -----


def test_legacy_unmigrated_memory_tree_is_visible_as_in_flight(tmp_path) -> None:
    """Review fix (issue #2094 follow-up): `_memory_root()`/
    `_find_in_flight_slugs()` used to look only under
    `.claude/memory/test-improve/`, never migrating a pre-existing
    top-level `memory/test-improve/<slug>/` tree the way
    `scripts/test_improve_resume.py`'s `resolve_memory_dir` does — so a run
    still under the legacy location was invisible to `_find_in_flight_slugs`
    and the guard silently failed open (allowed every phase-reference read)
    for it. This must resolve the legacy run once migrated, exactly like
    `--from-phase` auto-detect does."""
    legacy_dir = tmp_path / "memory" / "test-improve" / "my-repo"
    _make_phase_files(legacy_dir, "0", "2", "1", "4", "5")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.slug == "my-repo"
    assert result.phase == "6"
    # Moved, not copied - the legacy bare-path files are gone.
    assert not (legacy_dir / "phase-0.md").exists()
    new_dir = _memory_root(tmp_path) / "my-repo"
    assert (new_dir / "phase-0.md").is_file()


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

    assert result.status == "unresolved"
    assert result.reason == "malformed or missing phase-0.md"
    assert result.slug == "my-repo"


def test_missing_phase0_fails_open_even_outside_phase2_and_phase6(tmp_path) -> None:
    """Review fix (issue #2094 follow-up): the malformed/missing-phase-0.md
    check used to run only inside the highest=='2' and highest=='6' branches
    — a deleted phase-0.md (e.g. per SKILL.md's reset flow, which deletes
    only phase-0.md and leaves later phase files in place) with a highest
    completed phase outside that pair (e.g. '5', here) used to resolve
    confidently instead of failing open, unlike
    scripts/test_improve_resume.py's build_result(), which hard-requires
    phase-0.md for every resolution regardless of which phase is highest."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "2", "1", "4", "5")

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
    assert result.reason == guard.REASON_MALFORMED_PHASE0
    assert result.slug == "my-repo"
    assert result.highest == "5"


def test_unparseable_phase0_on_sole_candidate_fails_open(tmp_path) -> None:
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "2")
    _write_phase0_text(slug_dir, "not a key-value line\n")

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
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


def test_sanitize_for_message_strips_lone_surrogates(tmp_path) -> None:
    """Review fix (issue #2094 follow-up, round 15): `result.slug` and
    `file_path` can originate from a real on-disk directory/file name --
    on POSIX, Python decodes an arbitrary (non-UTF-8) filesystem byte
    sequence via `surrogateescape`, producing lone surrogates in the
    resulting `str`. Those aren't control characters, so the pre-fix
    `_CONTROL_CHARS_RE` didn't strip them, and `main()`'s message-emission
    loop (`print()`/`sys.stderr.write()`) -- which sits OUTSIDE `main()`'s
    own fail-open `try/except` -- would raise an uncaught
    `UnicodeEncodeError` on such a value, crashing the hook on its own
    BLOCK path. A sanitized value must always be safely UTF-8-encodable."""
    lone_surrogate = "my-repo-\udc80-slug"
    with pytest.raises(UnicodeEncodeError):
        lone_surrogate.encode("utf-8")

    sanitized = guard._sanitize_for_message(lone_surrogate)

    sanitized.encode("utf-8")  # must not raise
    assert "\udc80" not in sanitized


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
    _write_phase0_text(slug_dir, "refactor-mode: refactor-allowed\n")

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
    assert result.reason == guard.REASON_PHASE_6_7_AMBIGUOUS


def test_phase6_refactor_allowed_read_of_phase7_reference_is_allowed(tmp_path) -> None:
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6"
    )
    _write_phase0_text(slug_dir, "refactor-mode: refactor-allowed\n")

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
    _write_phase0_text(slug_dir, "refactor-mode: refactor-allowed\n")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.phase == "8"


def test_phase6_no_refactor_mode_resolves_normally_to_phase8(tmp_path) -> None:
    """The ordinary case (refactor-mode: no-refactor, the default) is
    unaffected by the Phase-6/7 ambiguity check."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6"
    )
    _write_phase0_text(slug_dir, "refactor-mode: no-refactor\n")

    result = guard._resolve(tmp_path)

    assert result.status == "ok"
    assert result.phase == "8"


def test_phase6_missing_phase0_fails_open_not_confident_phase8(tmp_path) -> None:
    """Review fix (issue #2094 follow-up): the highest=='6' branch used to
    call `_read_refactor_mode()` (returns `None` on a missing/unreadable
    phase-0.md) and compare it directly against `"refactor-allowed"` — a
    `None` != "refactor-allowed" fell through to the ordinary "no-refactor"
    resolution (active phase 8) with no fail-open, unlike the Phase-3
    correction two branches above, which explicitly fails open on the same
    failure class. A missing phase-0.md at highest=='6' must fail open
    (REASON_MALFORMED_PHASE0), not confidently resolve to phase 8."""
    _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6")
    (_memory_root(tmp_path) / "my-repo" / "phase-0.md").unlink()

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
    assert result.reason == guard.REASON_MALFORMED_PHASE0


def test_phase6_garbled_refactor_mode_fails_open_not_confident_phase8(tmp_path) -> None:
    """A truncated/garbled refactor-mode value (e.g. `refactor-mode: x`) must
    fail open, not be silently treated as "not refactor-allowed" (i.e.
    no-refactor)."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6"
    )
    _write_phase0_text(slug_dir, "refactor-mode: x\n")

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
    assert result.reason == guard.REASON_MALFORMED_PHASE0


def test_phase6_refactor_mode_value_must_be_on_the_same_line(tmp_path) -> None:
    """Review fix (issue #2094 follow-up): `_REFACTOR_MODE_RE` copy-pasted
    `_BINDING_MODE_RE`'s newline-crossing `\\s*` defect (`\\s` matches `\\n`)
    -- a truncated `refactor-mode:` line with no value on it picked up an
    unrelated token from a LATER line as its value instead of failing open
    via REASON_MALFORMED_PHASE0."""
    slug_dir = _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6"
    )
    _write_phase0_text(slug_dir, "refactor-mode:\nrefactor-allowed\n")

    result = guard._resolve(tmp_path)

    assert result.status == "unresolved"
    assert result.reason == guard.REASON_MALFORMED_PHASE0


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

    assert result.status == "unresolved"
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


# --- Review fix: phase-9-close-out-prompt.md is shared, "after phase 9" ---
# --- content, not the phase-9-report.md reference it used to alias with ---


def test_phase9_close_out_prompt_always_allowed_during_active_phase9(tmp_path) -> None:
    """Review fix (issue #2094 follow-up): `_PHASE_REF_BASENAME_RE` captures
    only the phase digit, so `phase-9-close-out-prompt.md` (SKILL.md's own
    "not one of the ten numbered phases" content — the `### After Phase 9`
    section) used to alias with `phase-9-report.md` (the real Phase-9
    reference) and match phase "9" too — wrongly letting the strict
    equality check treat the close-out prompt as interchangeable with the
    actual active-Phase-9 reference instead of the shared, always-readable
    content it actually is (mirrors `phase-0-approach-contract.md`,
    AC2: no resolution work, no audit line)."""
    _make_phase_files(
        _memory_root(tmp_path) / "my-repo", "0", "2", "1", "4", "5", "6", "7", "8"
    )
    _write_phase0(_memory_root(tmp_path) / "my-repo", "none")

    code, lines = guard.evaluate(
        "skills/test-improve/references/phase-9-close-out-prompt.md", tmp_path
    )

    assert (code, lines) == (0, [])
    assert _audit_events(tmp_path) == []


def test_phase9_report_still_gated_normally(tmp_path) -> None:
    """The real Phase-9 reference file is unaffected by the close-out-prompt
    exemption above — still blocked when read prematurely (Phase 5 active,
    not yet Phase 9)."""
    slug_dir = _make_phase_files(_memory_root(tmp_path) / "my-repo", "0", "2", "1", "4")
    _write_phase0(slug_dir, "none")

    code, _lines = guard.evaluate(
        "skills/test-improve/references/phase-9-report.md", tmp_path
    )

    assert code == 2
    events = _audit_events(tmp_path)
    assert events[0]["event"] == "block"


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


def test_symlinked_phase_reference_matches_resolved_target(
    tmp_path, monkeypatch
) -> None:
    """Review fix (round 16, security-review): a `phase-<m>-*.md`-named
    symlink living directly inside `references/` and pointing at a
    DIFFERENT real file in that same directory is gated by the RESOLVED
    target's phase, not by the literally-requested symlink name. A prior
    version of this function exempted any symlink from gating outright to
    avoid this basename mismatch — that over-corrected into a full,
    unaudited bypass (see `test_symlink_outside_references_dir_still_gated`
    below); gating on the resolved target closes it while keeping the
    match accurate to what `Read` will actually deliver."""
    fake_plugin_root = tmp_path / "plugin"
    references_dir = fake_plugin_root / "skills" / "test-improve" / "references"
    references_dir.mkdir(parents=True)
    real_target = references_dir / "phase-2-baseline.md"
    real_target.write_text("baseline content\n", encoding="utf-8")
    symlink = references_dir / "phase-9-report.md"
    symlink.symlink_to(real_target)

    monkeypatch.setattr(guard, "_plugin_root", lambda: fake_plugin_root)

    # The symlink resolves to phase-2-baseline.md — gating follows the
    # resolved target, matching the content Read will actually deliver,
    # not the literally-requested "phase-9-report.md" name.
    assert guard._match_phase_reference(str(symlink)) == "2"
    assert guard._match_phase_reference(str(real_target)) == "2"


def test_symlink_outside_references_dir_still_gated(tmp_path, monkeypatch) -> None:
    """Round 16 security-review finding: a symlink located ANYWHERE on
    disk (not just inside `references/`) that points at a real guarded
    `references/phase-<m>-*.md` file must still be gated by that file's
    phase — `Read` follows symlinks and delivers the resolved target's
    content regardless of where the symlink itself lives, so a prior
    version's blanket `candidate.is_symlink(): return None` exemption was
    a silent, unaudited bypass of the guard on its own intercepted
    channel (Read). Reproduces the exact exploit shape reported: a
    symlink outside the plugin tree entirely, pointing at a not-yet-
    reached phase's reference file."""
    fake_plugin_root = tmp_path / "plugin"
    references_dir = fake_plugin_root / "skills" / "test-improve" / "references"
    references_dir.mkdir(parents=True)
    real_target = references_dir / "phase-7-refactor.md"
    real_target.write_text("refactor content\n", encoding="utf-8")

    outside_dir = tmp_path / "elsewhere"
    outside_dir.mkdir()
    outside_symlink = outside_dir / "notes.md"
    outside_symlink.symlink_to(real_target)

    monkeypatch.setattr(guard, "_plugin_root", lambda: fake_plugin_root)

    assert guard._match_phase_reference(str(outside_symlink)) == "7"


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


def test_audit_swallows_non_os_error_from_append_line_locked(
    tmp_path, monkeypatch, capsys
) -> None:
    """Round 16 test-review finding: `audit()`'s docstring documents that it
    was deliberately broadened from `except OSError` to `except Exception`
    (issue #2094 follow-up) because it is `main()`'s LAST-RESORT call, made
    from inside `main()`'s own broad `except Exception` handler with no
    further try/except around it — so ANY exception escaping `audit()`,
    not only an `OSError`, would propagate uncaught and crash the hook.
    That contract had no fault-injection test proving it; every other
    documented review-fix in this diff does. Forces `append_line_locked`
    to raise a non-`OSError` (`RuntimeError`) to prove `audit()` swallows
    it and falls through to the stderr diagnostic rather than propagating."""
    monkeypatch.setattr(
        guard,
        "append_line_locked",
        mock.Mock(side_effect=RuntimeError("lock manager exploded")),
    )

    guard.audit(tmp_path, guard.EVENT_FAIL_OPEN, file="some/path.md")

    err = capsys.readouterr().err
    assert "failed to write audit line" in err
    assert "lock manager exploded" in err
    assert _audit_events(tmp_path) == []


def test_main_survives_audit_raising_non_os_error(tmp_path, monkeypatch, capsys) -> None:
    """End-to-end companion to the unit test above: even when BOTH the
    guard's own decision logic AND its last-resort `audit()` call fail,
    `main()` must still return 0 (fail open) rather than let the
    `RuntimeError` from `append_line_locked` propagate out of the process —
    the exact crash `audit()`'s `except Exception` broadening exists to
    prevent."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard, "read_stdin_json", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr(
        guard,
        "append_line_locked",
        mock.Mock(side_effect=RuntimeError("lock manager exploded")),
    )

    assert guard.main() == 0

    err = capsys.readouterr().err
    assert "failed to write audit line" in err
    assert _audit_events(tmp_path) == []


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
