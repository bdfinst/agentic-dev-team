#!/usr/bin/env bats
# Doc-inspection tests for the state-aware CodeGraph step in
# /init-dev-team. The command is an LLM-interpreted markdown spec; the
# only stable test surface is the literal strings the spec must contain.
# Each test pins one specific string the implementer must preserve.

CMD="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/commands/init-dev-team.md"

_contains() {
  local needle="$1"
  grep -qF -- "$needle" "$CMD"
}

# ---------------------------------------------------------------------------
# State classifier (entry to the CodeGraph step)
# ---------------------------------------------------------------------------

@test "state_classifier_installed_detection_documented" {
  _contains "command -v codegraph"
}

@test "state_classifier_initialized_detection_documented" {
  _contains '[ -d "${PWD}/.codegraph" ]'
}

# ---------------------------------------------------------------------------
# Install prompt branch (installed=false, initialized=false)
# ---------------------------------------------------------------------------

@test "install_prompt_text_present" {
  _contains "Install CodeGraph for code intelligence? (y/N)"
}

@test "install_accept_url_present" {
  _contains "https://github.com/colbymchenry/codegraph#installation"
}

# ---------------------------------------------------------------------------
# Init prompt branch (installed=true, initialized=false)
# ---------------------------------------------------------------------------

@test "init_prompt_text_present" {
  _contains "CodeGraph is installed but not initialized in this project. Initialize now? (y/N)"
}

@test "init_run_command_documented" {
  _contains "codegraph init -i"
}

@test "init_run_announcement_present" {
  _contains "Running 'codegraph init -i' in this project..."
}

@test "init_success_message_present" {
  _contains "CodeGraph: initialized ✓"
}

@test "init_failure_message_present" {
  _contains "CodeGraph init failed (exit code"
}

# ---------------------------------------------------------------------------
# Skip-note texts (state-aware re-runs)
# ---------------------------------------------------------------------------

@test "decline_install_skip_note_text" {
  _contains "CodeGraph: previously declined install (remove the codegraph key from .claude/init-state.json to re-prompt)"
}

@test "decline_init_skip_note_text" {
  _contains "CodeGraph: previously declined init (remove the codegraph key from .claude/init-state.json to re-prompt)"
}

# ---------------------------------------------------------------------------
# State keys + stale-state override
# ---------------------------------------------------------------------------

@test "state_keys_install_accepted_documented" {
  _contains "install_accepted"
}

@test "state_keys_install_declined_documented" {
  _contains "install_declined"
}

@test "state_keys_init_accepted_documented" {
  _contains "init_accepted"
}

@test "state_keys_init_declined_documented" {
  _contains "init_declined"
}

@test "stale_state_override_documented" {
  # The doc must explain that install_declined is ignored when installed=true
  # AND init_declined is ignored when initialized=true. We check for a single
  # heading that introduces this rule.
  _contains "Stale-state override"
}

# ---------------------------------------------------------------------------
# Step 9 — JS bootstrap via js-project-init when no package.json
# ---------------------------------------------------------------------------

@test "js_bootstrap_check_present" {
  _contains 'test -f package.json'
}

@test "js_bootstrap_announcement_present" {
  _contains "No package.json found. Running /agentic-dev-team:js-project-init first to scaffold the project."
}

@test "js_bootstrap_invokes_skill" {
  _contains "/agentic-dev-team:js-project-init"
}

@test "js_abort_message_present" {
  _contains "Stryker skipped — no package.json. Re-run /init-dev-team after scaffolding your JS project."
}

@test "js_failure_message_present" {
  _contains "Stryker skipped — js-project-init failed. See errors above and re-run /init-dev-team after resolving them."
}

@test "js_package_present_path_unchanged" {
  # The pre-existing 'Check if already installed (project-local)' section must
  # still be present and follow the new bootstrap block.
  _contains "Check if already installed (project-local)"
}
