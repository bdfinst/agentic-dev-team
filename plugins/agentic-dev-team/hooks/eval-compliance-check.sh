#!/usr/bin/env bash
#
# eval-compliance-check.sh - Claude Code PostToolUse hook
#
# Fires after Write or Edit on any file. Runs structural checks on agent/command
# files and emits targeted doc-sync reminders for config and general repo changes.
#
# Input: JSON on stdin with tool_input.file_path
# Output: Feedback on stdout (shown to Claude as hook feedback)
# Exit 0: Always (advisory, never blocks)

set -uo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

# Classify file type for targeted checks
case "$FILE_PATH" in
  */agents/*.md) FILE_TYPE="agent" ;;
  */commands/*.md) FILE_TYPE="skill" ;;
  */.claude/hooks/*.sh|*/.claude/settings.json|*/CLAUDE.md) FILE_TYPE="config" ;;
  *) FILE_TYPE="other" ;;
esac

if [ ! -f "$FILE_PATH" ]; then
  exit 0  # file gone
fi

CONTENT=$(cat "$FILE_PATH")
WARNINGS=""
FAILS=""

fail() {
  FAILS="${FAILS}  FAIL: $1\n"
}

warn() {
  WARNINGS="${WARNINGS}  WARN: $1\n"
}

# --- Agent checks ---
if [ "$FILE_TYPE" = "agent" ]; then
  AGENT_NAME=$(basename "$FILE_PATH" .md)

  # 1. Structured output format (FAIL)
  if ! echo "$CONTENT" | grep -qiE 'output.*json|json.*output|status.*pass.*warn.*fail'; then
    fail "$AGENT_NAME: Missing structured output format (must include status/issues/summary JSON schema)."
  fi

  # 2. Severity definitions (FAIL)
  if ! echo "$CONTENT" | grep -qiE 'severity.*error.*warning|error.*warning.*suggestion'; then
    fail "$AGENT_NAME: Missing severity definitions (must define error/warning/suggestion)."
  fi

  # 3. Detection rules (WARN)
  if ! echo "$CONTENT" | grep -qiE '## Detect|## Check|## Rules'; then
    warn "$AGENT_NAME: Missing detection rules section."
  fi

  # 4. Scope boundaries (WARN)
  if ! echo "$CONTENT" | grep -qiE '## Ignore|handled by other'; then
    warn "$AGENT_NAME: Missing scope boundaries (what does this agent NOT check?)."
  fi

  # 5. Self-describing: must not depend on external config (FAIL)
  if echo "$CONTENT" | grep -qiE 'config.*json|review-config|config/'; then
    fail "$AGENT_NAME: References external config file. Agents must be self-describing — declare thresholds, file scope, and defaults inline."
  fi

  # 7. Skip support (WARN)
  if ! echo "$CONTENT" | grep -qiE '## Skip'; then
    warn "$AGENT_NAME: Missing ## Skip section (must define when agent is inapplicable)."
  fi

  # 8. Model tier (WARN)
  if ! echo "$CONTENT" | grep -qiE 'model tier:\s*(small|mid|frontier)'; then
    warn "$AGENT_NAME: Missing 'Model tier' field (must be small, mid, or frontier)."
  fi

  # 9. Context needs (WARN)
  if ! echo "$CONTENT" | grep -qiE 'context needs:\s*(diff-only|full-file|project-structure)'; then
    warn "$AGENT_NAME: Missing 'Context needs' field (must be diff-only, full-file, or project-structure)."
  fi

  # 6. File scope for language-specific agents (WARN)
  if echo "$CONTENT" | grep -qiE 'javascript\|typescript\|python\|ruby\|go\|rust\|java'; then
    if ! echo "$CONTENT" | grep -qiE 'scope:|\.js\b|\.ts\b|\.py\b|\.rb\b|\.go\b|\.rs\b|\.java\b|files only'; then
      warn "$AGENT_NAME: Mentions a language but doesn't declare file scope (e.g., 'Scope: *.js, *.ts files only')."
    fi
  fi

  # Always require /agent-audit and doc sync after agent changes
  printf "\n"
  if [ -n "$FAILS" ]; then
    printf "$FAILS"
  fi
  if [ -n "$WARNINGS" ]; then
    printf "$WARNINGS"
  fi
  printf "\n"
  printf "  Agent file changed: $AGENT_NAME\n"
  printf "  ACTION REQUIRED: Run /agent-audit $FILE_PATH\n"
  printf "  DOC SYNC REQUIRED: Update .claude/CLAUDE.md and docs/agent_info.md to reflect any changes.\n"
  printf "  Invoke the tech-writer persona to review affected documentation before marking this task complete.\n"
fi

# --- Skill checks ---
if [ "$FILE_TYPE" = "skill" ]; then
  SKILL_NAME=$(basename "$FILE_PATH" .md)

  # 1. Role declaration (WARN)
  if ! echo "$CONTENT" | grep -qiE 'role:\s*(orchestrator|worker|implementation)'; then
    warn "$SKILL_NAME: Missing 'Role:' declaration (must be orchestrator, worker, or implementation)."
  fi

  # 2. Constraints section (WARN)
  if ! echo "$CONTENT" | grep -qiE 'constraints'; then
    warn "$SKILL_NAME: Missing constraints section for role boundaries."
  fi

  # 3. Conciseness directive (WARN)
  if ! echo "$CONTENT" | grep -qiE 'be concise|concise'; then
    warn "$SKILL_NAME: Missing conciseness directive (must instruct concise output to reduce token usage)."
  fi

  # 4. Structured steps (FAIL)
  if ! echo "$CONTENT" | grep -qE '### [0-9]+\.|## Steps'; then
    fail "$SKILL_NAME: Missing numbered steps."
  fi

  # 4. Argument parsing (WARN)
  if ! echo "$CONTENT" | grep -qiE 'argument|parse|args'; then
    warn "$SKILL_NAME: Missing argument parsing section."
  fi

  # 5. Output/report section (WARN)
  if echo "$CONTENT" | grep -qiE 'review|audit|fix'; then
    if ! echo "$CONTENT" | grep -qiE 'report|summary|output'; then
      warn "$SKILL_NAME: Review-related skill missing report/summary section."
    fi
  fi

  if [ -n "$FAILS" ] || [ -n "$WARNINGS" ]; then
    printf "\n"
    if [ -n "$FAILS" ]; then
      printf "$FAILS"
    fi
    if [ -n "$WARNINGS" ]; then
      printf "$WARNINGS"
    fi
    printf "\n"
    printf "  Run /agent-audit for a full compliance report.\n"
  fi
fi

# --- Config file changes (hooks, settings, CLAUDE.md) ---
if [ "$FILE_TYPE" = "config" ]; then
  CONFIG_NAME=$(basename "$FILE_PATH")
  printf "\n"
  printf "  Config file changed: $CONFIG_NAME\n"
  printf "  DOC SYNC REQUIRED: Verify affected documentation is current:\n"
  case "$FILE_PATH" in
    */hooks/*.sh)
      printf "    - CLAUDE.md (hooks section)\n"
      printf "    - docs/architecture.md (Governance section)\n"
      ;;
    */settings.json)
      printf "    - CLAUDE.md (plugins/commands registry)\n"
      printf "    - docs/architecture.md (Governance section)\n"
      ;;
    */CLAUDE.md)
      printf "    - docs/ (any section that mirrors CLAUDE.md tables)\n"
      ;;
  esac
  printf "  Invoke the tech-writer persona to review before marking the task complete.\n"
fi

# --- General repo changes ---
if [ "$FILE_TYPE" = "other" ]; then
  # Skip lock files, generated files, memory, metrics, evals, and docs themselves
  case "$FILE_PATH" in
    *lock*|*/memory/*|*/metrics/*|*/evals/*|*.log|*/docs/*.md|*/README*) exit 0 ;;
    *) ;;
  esac

  CHANGED_NAME=$(basename "$FILE_PATH")
  printf "\n"
  printf "  File changed: $CHANGED_NAME\n"
  printf "  DOC SYNC CHECK: If this change affects observable behavior or architecture, update:\n"
  printf "    - docs/architecture.md (system design or configuration changes)\n"
  printf "    - README.md            (top-level changes visible to new users)\n"
  printf "  Invoke the tech-writer persona to confirm docs are current before closing the task.\n"
fi

exit 0
