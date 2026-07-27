"""Issue #553 — plans/build-worktree-inherits-caller-head.md Slice 1.

Step 1.1: plugins/dev-team/scripts/build_worktree_baseref.py `detect`
subcommand. Prints exactly one of head|fresh|unset|unknown and exits 0
(degrade-never-abort — the same posture the now-retired
hooks/lib/model_resolve.py used before ADR 0026 removed it).

Env var seam (test-only injection, the same pattern the retired
model-resolve.sh used via MODEL_ROUTING_JSON/MODEL_LADDER_JSON):
  BASEREF_SETTINGS_PATHS — colon-separated list of settings files,
  highest precedence first. When unset, the script falls back to its
  real default order (.claude/settings.json → ~/.claude/settings.json).

Step 1.2: SKILL.md Step 4 documents the pre-dispatch detect-and-warn
wire-up. Doc-grep tests only — no subagent dispatch here.

Note (issue #674 port): the bats original invoked the script with
`run bash "$SCRIPT" detect` even though `build_worktree_baseref.py` is a
Python script (a leftover from the #587/#572 .sh→.py rename that the
bats file's own invocation never caught up with — `bash` can't execute a
Python shebang, so every `detect`-invoking assertion silently failed on
main; tests/skills/ isn't wired into any CI gate, so nobody noticed). The
pattern this epic (#674) prescribes — `subprocess.run([sys.executable,
str(SCRIPT), ...])` — is exactly the fix: invoke the script the way the
issue's own `Pattern` section specifies. Two more assertions are updated
to match the current shipped implementation:
  - the `jq`-unavailable → `unknown` scenario no longer applies: the
    Python port is stdlib-only (no jq dependency at all — `unknown` is
    reserved for future contract expansion per the script's own
    docstring). The equivalent-spirit check here asserts the script has
    no jq dependency instead of exercising a code path that no longer
    exists.
  - the SKILL.md doc-grep test for the script's on-disk filename now
    checks the current `build_worktree_baseref.py`, not the retired
    `.sh` name.

Ported from tests/skills/build_worktree_baseref_detect_tests.bats
(issue #674).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section

SCRIPT = PLUGIN_ROOT / "scripts" / "build_worktree_baseref.py"
BUILD_SKILL = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"


def _detect(
    tmp_path: Path, settings_paths: str | None = None
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if settings_paths is not None:
        env["BASEREF_SETTINGS_PATHS"] = settings_paths
    return subprocess.run(
        [sys.executable, str(SCRIPT), "detect"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Step 1.1 — detect subcommand
# ---------------------------------------------------------------------------


def test_detect_explicit_head_in_the_highest_precedence_file_prints_head(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"worktree": {"baseRef": "head"}}')
    result = _detect(tmp_path, str(settings))
    assert result.returncode == 0
    assert result.stdout.strip() == "head"


def test_detect_explicit_fresh_in_the_highest_precedence_file_prints_fresh(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"worktree": {"baseRef": "fresh"}}')
    result = _detect(tmp_path, str(settings))
    assert result.returncode == 0
    assert result.stdout.strip() == "fresh"


def test_detect_key_absent_from_every_file_prints_unset_not_unknown(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"permissions": {}}')
    result = _detect(tmp_path, str(settings))
    assert result.returncode == 0
    assert result.stdout.strip() == "unset"


def test_detect_no_settings_files_exist_at_all_prints_unset(tmp_path):
    result = _detect(tmp_path, str(tmp_path / "does-not-exist.json"))
    assert result.returncode == 0
    assert result.stdout.strip() == "unset"


def test_detect_two_valid_files_disagree_highest_precedence_file_wins_head_over_fresh(
    tmp_path,
):
    high = tmp_path / "high.json"
    high.write_text('{"worktree": {"baseRef": "head"}}')
    low = tmp_path / "low.json"
    low.write_text('{"worktree": {"baseRef": "fresh"}}')
    result = _detect(tmp_path, f"{high}:{low}")
    assert result.returncode == 0
    assert result.stdout.strip() == "head"


def test_detect_two_valid_files_disagree_reverse_order_confirms_precedence_not_alphabetical(
    tmp_path,
):
    # Same fixture, reversed precedence order. If the script were merging
    # by filename or picking a "winner" some other way, one of these two
    # assertions would break. Paired-order coverage proves precedence is
    # what drives the result.
    a = tmp_path / "a.json"
    a.write_text('{"worktree": {"baseRef": "fresh"}}')
    b = tmp_path / "b.json"
    b.write_text('{"worktree": {"baseRef": "head"}}')

    # b.json first (higher precedence) → head wins
    result = _detect(tmp_path, f"{b}:{a}")
    assert result.returncode == 0
    assert result.stdout.strip() == "head"

    # a.json first (higher precedence) → fresh wins
    result = _detect(tmp_path, f"{a}:{b}")
    assert result.returncode == 0
    assert result.stdout.strip() == "fresh"


def test_detect_malformed_json_in_the_highest_precedence_file_falls_back_to_a_lower_valid_file(
    tmp_path,
):
    broken = tmp_path / "broken.json"
    broken.write_text("{not valid json")
    valid = tmp_path / "valid.json"
    valid.write_text('{"worktree": {"baseRef": "head"}}')
    result = _detect(tmp_path, f"{broken}:{valid}")
    assert result.returncode == 0
    assert result.stdout.strip() == "head"


def test_detect_script_has_no_jq_dependency():
    # The bats original exercised a `command -v jq`-unavailable PATH shim
    # to assert the .sh's fail-safe "unknown" output. The Python port
    # (#587) is stdlib-only — no external tool dependency, so there is no
    # jq-unavailable code path left to exercise. Assert the invariant that
    # replaced it instead: the script never shells out to jq.
    assert "subprocess" not in SCRIPT.read_text()
    assert '"jq"' not in SCRIPT.read_text()


def test_detect_prints_exactly_one_line(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"worktree": {"baseRef": "fresh"}}')
    result = _detect(tmp_path, str(settings))
    assert result.returncode == 0
    assert result.stdout.count("\n") <= 1


def test_detect_unknown_subcommand_exits_non_zero_with_usage(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "bogus"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Step 1.2 — /build Step 4 wire-up (doc-grep — no subagent dispatch)
# ---------------------------------------------------------------------------


def _step_4_section() -> str:
    return section(
        BUILD_SKILL.read_text(),
        r"^### 4\. ",
        boundary_pattern=r"^### 5\. ",
        include_start_line=False,
    )


def test_skill_md_step_4_documents_a_pre_dispatch_base_ref_check():
    text = BUILD_SKILL.read_text()
    assert grep(r"build_worktree_baseref\.py", text, ignore_case=True)
    assert grep(r"base-ref check", text, ignore_case=True)


def test_skill_md_step_4_base_ref_check_mentions_the_settings_file_the_setting_head_and_the_opt_out_env_var():
    s = _step_4_section()
    assert ".claude/settings.json" in s
    assert "worktree.baseRef" in s
    assert "head" in s
    assert "DEV_TEAM_WORKTREE_BASE_FRESH" in s


def test_skill_md_step_4_base_ref_check_includes_a_paste_ready_json_snippet():
    s = _step_4_section()
    assert '"worktree"' in s
    assert '"baseRef"' in s


def test_skill_md_step_4_states_the_check_runs_in_the_top_level_session_before_any_subagent_dispatch():
    s = _step_4_section()
    assert grep(r"before any subagent dispatch|before dispatch", s, ignore_case=True)
    assert grep(r"top-level", s, ignore_case=True)


def test_skill_md_step_4_states_build_never_mutates_a_settings_file():
    assert grep(
        r"never mutat|no.*mutation|does not mutate|no settings mutation",
        _step_4_section(),
        ignore_case=True,
    )


def test_skill_md_step_4_documents_that_the_opt_out_env_var_silences_the_warning_ac3_suppression():
    # Distinct from the generic "the env var name appears somewhere in
    # Step 4" check earlier — this one specifically asserts the
    # *suppression semantics* of DEV_TEAM_WORKTREE_BASE_FRESH=1 are
    # documented (i.e. the doc actually says setting it produces no
    # warning). Guards spec AC3.
    s = _step_4_section()
    assert grep_multiline(
        r"DEV_TEAM_WORKTREE_BASE_FRESH[^`]{0,200}?(silence|suppress|no warning|skip|disable|opt.?out)",
        s,
        ignore_case=True,
    ) or grep_multiline(
        r"(silence|suppress|no warning|skip|disable|opt.?out)[^`]{0,200}?DEV_TEAM_WORKTREE_BASE_FRESH",
        s,
        ignore_case=True,
    )
