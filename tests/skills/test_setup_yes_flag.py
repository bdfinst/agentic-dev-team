"""#1234 — the unattended `/setup --yes` flag.

`--yes` is skill-markdown (prompt) behavior, so it is verified the way the
repo verifies its other cross-skill contracts: assert the required strings
appear in `setup/SKILL.md` and `project-init/SKILL.md`.

Contract:

1. Both skills advertise `--yes` in their `argument-hint` frontmatter.
2. `/setup` documents the affirmative gates it auto-confirms, the conservative
   gates it skips (existing CLAUDE.md, coverage-config edits, Graphify,
   ambiguous stack), the `--dry-run` precedence, and passing `--yes` through
   to `/project-init`.
3. `/project-init` documents an Arguments section: affirmative gates
   (three-column plan, capability tools, keyless pair) and conservative ones
   (Graphify skip with no durable decline, zero/ambiguous stack exit).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    collapsed,
    grep,
    section_outside_code,
)

SETUP = PLUGIN_ROOT / "skills" / "setup" / "SKILL.md"
PROJECT_INIT = PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md"


def _setup() -> str:
    return SETUP.read_text(encoding="utf-8")


def _project_init() -> str:
    return PROJECT_INIT.read_text(encoding="utf-8")


def _yes_semantics_conservative_repowise_bullet() -> str:
    """Bound to just the Conservative bucket's `Step 4c Repowise` bullet —
    not the whole document — so a match here can't be satisfied by an
    earlier, unrelated occurrence of "Repowise" (e.g. the Affirmative-bucket
    CodeGraph bullet) or a later occurrence of the target phrase belonging
    to a sibling bullet (e.g. Graphify's own "does not record a durable
    decline" clause). Mirrors the identical helper already added in
    tests/skills/test_project_init_repowise_claude_md_write.py, #1690."""
    return section_outside_code(
        _project_init(),
        r"^- \*\*Step 4c Repowise",
        boundary_pattern=r"^- \*\*Step 1 zero/ambiguous stack",
        include_start_line=True,
    )


def _yes_semantics_conservative_concise_preference_bullet() -> str:
    """Bound to just the Conservative bucket's `Concise-response preference`
    bullet (the last one in that bucket) — not the whole document — so this
    can't be satisfied by Step 8a's own, unrelated "never guess a
    communication-style preference" sentence in its own prose section
    (a real gap a prior version of this test had: it matched the whole
    document, so deleting this bullet entirely would still pass)."""
    return section_outside_code(
        _setup(),
        r"^- \*\*Concise-response preference",
        boundary_pattern=r"^\*\*Precedence\.",
        include_start_line=True,
    )


# --- argument-hint frontmatter -----------------------------------------------


def test_setup_argument_hint_lists_yes_and_dry_run():
    assert grep(r'^argument-hint:.*--yes.*--dry-run', _setup())


def test_project_init_argument_hint_lists_yes():
    assert grep(r'^argument-hint:.*--yes', _project_init())


# --- /setup: affirmative + conservative gates --------------------------------


def test_setup_passes_yes_through_to_project_init():
    body = collapsed(_setup())
    assert "/dev-team:project-init --yes" in body


def test_setup_never_overwrites_existing_claude_md_under_yes():
    body = collapsed(_setup())
    # The Step 8 gate must state the skip branch is taken under --yes.
    assert grep(r"skip branch", body) or "left unchanged" in body
    assert "--yes" in body


def test_setup_coverage_config_edits_stay_advisory_under_yes():
    body = collapsed(_setup())
    # additive provider install is allowed; --patch / hand-edits are not.
    assert "@vitest/coverage-v8" in body
    assert grep(r"do \*\*not\*\* run `--patch`|does \*\*not\*\* run `--patch`", body)


def test_setup_never_guesses_stack_under_yes():
    body = collapsed(_setup())
    assert grep(r"never guess a stack", body)


def test_setup_never_guesses_communication_style_under_yes():
    bullet = collapsed(_yes_semantics_conservative_concise_preference_bullet())
    assert grep(r"never guesses a communication-style preference", bullet)
    assert "concise-preference-skipped-under-yes" in bullet


def test_setup_dry_run_beats_yes():
    body = collapsed(_setup())
    assert grep(r"`--dry-run` wins", body)
    assert grep(r"`--yes` ignored under `--dry-run`", body)


# --- /project-init: Arguments section ----------------------------------------


def test_project_init_has_arguments_section():
    assert grep(r"^## Arguments", _project_init())


def test_project_init_yes_auto_confirms_plan_and_keyless_pair():
    body = collapsed(_project_init())
    assert grep(r"three-column plan.*proceed|print the\s*plan and proceed", body)
    assert grep(r"keyless[- ]pair prompt as yes|keyless pair \(CodeGraph \+ Repowise\)", body)


def test_project_init_yes_skips_graphify_without_durable_decline():
    body = collapsed(_project_init())
    assert grep(r"skip Graphify for this run", body)
    assert grep(r"not record a durable decline", body)


def test_project_init_yes_exits_on_ambiguous_stack():
    body = collapsed(_project_init())
    assert grep(r"[Uu]nder `--yes`, do not prompt", body)
    assert grep(r"never guess a stack", body)


# --- /project-init: Repowise moved to the Conservative bucket (#1690),
# matching Graphify's own `--yes`-skip treatment ---------------------------


def test_project_init_yes_skips_repowise_without_durable_decline():
    bullet = collapsed(_yes_semantics_conservative_repowise_bullet())
    assert grep(r"Repowise: skipped under --yes", bullet)
    assert grep(r"not\*\* record a durable decline", bullet)


def test_project_init_yes_keeps_codegraph_affirmative_only():
    body = collapsed(_project_init())
    assert grep(r"Step 4c CodeGraph.*already yes", body)
    assert grep(r"Repowise.*does \*\*not\*\* stay", body)
