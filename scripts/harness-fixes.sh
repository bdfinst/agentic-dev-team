#!/usr/bin/env bash
# harness-fixes.sh — apply harness-audit-2026-06-23 recommendations
#
# Usage:
#   bash scripts/harness-fixes.sh            # run all automatable steps
#   bash scripts/harness-fixes.sh --dry-run  # preview only, no writes
#   bash scripts/harness-fixes.sh --step 1   # run one step by number
#
# Steps that require /agent-eval validation or external-plugin changes
# are printed as instructions rather than applied automatically.
#
# Exit codes: 0 = success, 1 = prerequisite missing, 2 = user abort

set -uo pipefail

# ── Args ──────────────────────────────────────────────────────────────────────
DRY_RUN=false
ONLY_STEP=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --step)    shift; ONLY_STEP="${1:-}" ;;
    --step=*)  ONLY_STEP="${arg#--step=}" ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
PLUGIN_DIR="plugins/dev-team"
HOOKS_DIR="$PLUGIN_DIR/hooks"
SETTINGS="$PLUGIN_DIR/settings.json"
SCRIPTS_DIR="scripts"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'

step_num=0
step_skipped=0
step_applied=0
step_manual=0

header() {
  step_num=$((step_num + 1))
  echo
  echo -e "${BOLD}${CYAN}Step $step_num: $1${RESET}"
}

skip_step() {
  echo -e "  ${YELLOW}SKIP${RESET} — $1"
  step_skipped=$((step_skipped + 1))
}

applied() {
  echo -e "  ${GREEN}APPLIED${RESET} — $1"
  step_applied=$((step_applied + 1))
}

manual() {
  echo -e "  ${YELLOW}MANUAL${RESET} — $1"
  step_manual=$((step_manual + 1))
}

write_file() {   # write_file <path> <content-heredoc>
  local path="$1"; shift
  if $DRY_RUN; then
    echo -e "  ${YELLOW}[DRY RUN]${RESET} would write: $path"
  else
    mkdir -p "$(dirname "$path")"
    cat > "$path"
    applied "wrote $path"
  fi
}

should_run() {   # should_run <num>: returns 0 if this step should execute
  [ -z "$ONLY_STEP" ] || [ "$ONLY_STEP" = "$step_num" ]
}

require_file() {
  if [ ! -f "$1" ]; then
    echo -e "  ${RED}ERROR${RESET}: required file not found: $1"
    exit 1
  fi
}

# ── Prerequisites ─────────────────────────────────────────────────────────────
echo -e "${BOLD}Harness Fixes — agentic-dev-team${RESET}"
echo "Source: harness-audit-2026-06-23.md + session-review-2026-06-23.md"
$DRY_RUN && echo -e "${YELLOW}DRY RUN mode — no files will be written${RESET}"

require_file "$PLUGIN_DIR/hooks/pre-tool-guard.sh"
require_file "$SETTINGS"
require_file "$PLUGIN_DIR/scripts/session_report.py"
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq required"; exit 1; }

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE A — Automatable code changes
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo -e "${BOLD}── Phase A: Automatable code changes ──${RESET}"

# ─────────────────────────────────────────────────────────────────────────────
header "Create verify-guard hook (stop spinning verify loops)"
# Source: session-review finding #1, harness-audit §orchestration
# 907 repeated verify runs across 268 sessions (3.4/session).
# Hook fires as PreToolUse on Bash; uses a per-session temp file to count
# consecutive identical verify invocations; warns at ≥3 consecutive runs.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  if [ -f "$HOOKS_DIR/verify-guard.sh" ]; then
    skip_step "verify-guard.sh already exists"
  else
    write_file "$HOOKS_DIR/verify-guard.sh" << 'HOOK'
#!/usr/bin/env bash
# verify-guard.sh — Claude Code PreToolUse hook
#
# Detects repeated identical verify invocations within a session and emits
# a convergence warning after THRESHOLD consecutive identical runs, nudging
# the agent to change approach rather than re-running the same failing command.
#
# Input:  JSON on stdin (hook_event_name, session_id, tool_input.command, cwd)
# Output: Warning on stdout; always exit 0 (advisory, never blocks)
# Threshold: DEV_TEAM_VERIFY_THRESHOLD (default 3)

set -uo pipefail

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -z "$CMD" ] && exit 0

# Only fire on verify-class commands (mirrors session_report.py/session_log.classify _VERIFY_RE)
if ! echo "$CMD" | grep -qE \
  '\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|go test|cargo (test|build)|mvn|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck)\b'; then
  exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
# Derive a stable key: prefer session_id, fall back to cwd hash
if [ -n "$SESSION_ID" ]; then
  STATE_KEY="$SESSION_ID"
else
  STATE_KEY=$(echo "${CWD:-$PWD}" | cksum | cut -d' ' -f1)
fi

STATE_DIR="${TMPDIR:-/tmp}/dev-team-verify-guard"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/${STATE_KEY}.json"

# Normalize the command (collapse whitespace) for comparison
NORM_CMD=$(echo "$CMD" | tr -s '[:space:]' ' ' | sed 's/^ //;s/ $//')
NORM_HASH=$(echo "$NORM_CMD" | cksum | cut -d' ' -f1)

THRESHOLD="${DEV_TEAM_VERIFY_THRESHOLD:-3}"

# Read current state
prev_hash=""
count=0
if [ -f "$STATE_FILE" ] && command -v jq >/dev/null 2>&1; then
  prev_hash=$(jq -r '.hash // empty' "$STATE_FILE" 2>/dev/null || true)
  count=$(jq -r '.count // 0' "$STATE_FILE" 2>/dev/null || echo 0)
fi

# Update count: increment if same command, reset if different
if [ "$NORM_HASH" = "$prev_hash" ]; then
  count=$((count + 1))
else
  count=1
fi

# Write updated state
jq -nc --arg h "$NORM_HASH" --argjson c "$count" '{"hash":$h,"count":$c}' \
  > "$STATE_FILE" 2>/dev/null || true

# Warn if threshold exceeded
if [ "$count" -ge "$THRESHOLD" ]; then
  echo "verify-guard: This verify command has run ${count} consecutive times without a code change."
  echo "  If the tests are still failing, change the code rather than re-running the same command."
  echo "  To suppress this warning, set DEV_TEAM_VERIFY_THRESHOLD=0."
fi

exit 0
HOOK
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Create bash-retry-guard hook (warn on repeated identical Bash commands)"
# Source: session-review finding #2, harness-audit §orchestration
# 457 retried bash commands across 268 sessions (1.7/session).
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  if [ -f "$HOOKS_DIR/bash-retry-guard.sh" ]; then
    skip_step "bash-retry-guard.sh already exists"
  else
    write_file "$HOOKS_DIR/bash-retry-guard.sh" << 'HOOK'
#!/usr/bin/env bash
# bash-retry-guard.sh — Claude Code PreToolUse hook
#
# Detects repeated identical Bash commands within a session. After
# THRESHOLD consecutive identical commands, nudges the agent to vary
# its approach rather than re-running the same failing command.
#
# Input:  JSON on stdin (session_id, tool_input.command, cwd)
# Output: Warning on stdout; always exit 0 (advisory, never blocks)
# Threshold: DEV_TEAM_BASH_RETRY_THRESHOLD (default 3)

set -uo pipefail

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -z "$CMD" ] && exit 0

# Exclude verify commands (verify-guard handles those)
if echo "$CMD" | grep -qE \
  '\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|go test|cargo (test|build)|mvn|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck)\b'; then
  exit 0
fi

# Exclude trivially short/read-only commands — they retry harmlessly
TRIMMED=$(echo "$CMD" | tr -s '[:space:]' ' ' | sed 's/^ //;s/ $//')
case "$TRIMMED" in
  ls|ls\ *|pwd|echo\ *|cat\ *|head\ *|tail\ *|grep\ *) exit 0 ;;
esac

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
if [ -n "$SESSION_ID" ]; then
  STATE_KEY="$SESSION_ID"
else
  STATE_KEY=$(echo "${CWD:-$PWD}" | cksum | cut -d' ' -f1)
fi

STATE_DIR="${TMPDIR:-/tmp}/dev-team-bash-retry"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/${STATE_KEY}.json"

NORM_HASH=$(echo "$TRIMMED" | cksum | cut -d' ' -f1)
THRESHOLD="${DEV_TEAM_BASH_RETRY_THRESHOLD:-3}"

prev_hash=""
count=0
if [ -f "$STATE_FILE" ]; then
  prev_hash=$(jq -r '.hash // empty' "$STATE_FILE" 2>/dev/null || true)
  count=$(jq -r '.count // 0' "$STATE_FILE" 2>/dev/null || echo 0)
fi

if [ "$NORM_HASH" = "$prev_hash" ]; then
  count=$((count + 1))
else
  count=1
fi

jq -nc --arg h "$NORM_HASH" --argjson c "$count" '{"hash":$h,"count":$c}' \
  > "$STATE_FILE" 2>/dev/null || true

if [ "$count" -ge "$THRESHOLD" ]; then
  echo "bash-retry-guard: This command has run ${count} consecutive times."
  echo "  If it keeps failing, investigate the root cause rather than retrying."
  echo "  Set DEV_TEAM_BASH_RETRY_THRESHOLD=0 to disable this warning."
fi

exit 0
HOOK
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Register new hooks in settings.json"
# Add verify-guard and bash-retry-guard to PreToolUse Bash hooks
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  # Check if already registered
  if jq -e '.hooks.PreToolUse[] | .hooks[]? | select(.command | test("verify-guard"))' \
      "$SETTINGS" >/dev/null 2>&1; then
    skip_step "verify-guard already registered in settings.json"
  else
    if $DRY_RUN; then
      echo -e "  ${YELLOW}[DRY RUN]${RESET} would add verify-guard.sh and bash-retry-guard.sh to PreToolUse Bash hooks in $SETTINGS"
    else
      # Insert both new hooks into the Bash PreToolUse block
      python3 - "$SETTINGS" << 'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)

new_hooks = [
    {"type": "command", "command": "bash hooks/verify-guard.sh"},
    {"type": "command", "command": "bash hooks/bash-retry-guard.sh"},
]

for block in cfg["hooks"].get("PreToolUse", []):
    matcher = block.get("matcher", "")
    if "Bash" in str(matcher):
        existing = [h["command"] for h in block.get("hooks", [])]
        for nh in new_hooks:
            if nh["command"] not in existing:
                block["hooks"].append(nh)
        break

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY
      applied "registered verify-guard.sh and bash-retry-guard.sh in $SETTINGS"
    fi
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Fix namespace stripping in session_report.py"
# _strip_ns() only strips 'dev-team:' prefix. Invocations using
# 'agentic-dev-team:' are not normalized, inflating never_observed lists
# and double-counting agents across plugin namespaces.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  EXTRACT="$PLUGIN_DIR/scripts/session_report.py"
  if grep -q "agentic-dev-team:" "$EXTRACT"; then
    skip_step "agentic-dev-team namespace already handled in session_report.py"
  else
    if $DRY_RUN; then
      echo -e "  ${YELLOW}[DRY RUN]${RESET} would update _strip_ns() in $EXTRACT to strip 'agentic-dev-team:' prefix"
    else
      python3 - "$EXTRACT" << 'PY'
import sys
path = sys.argv[1]
with open(path) as f:
    src = f.read()

old = '''def _strip_ns(name: str) -> str:
    """Drop the dev-team plugin namespace so invoked names match the registry
    (registry entries are bare dir/file stems). `dev-team:plan` -> `plan`;
    other-plugin or built-in names (`update-config`, `Explore`) pass through."""
    return name[len("dev-team:"):] if name.startswith("dev-team:") else name'''

new = '''def _strip_ns(name: str) -> str:
    """Drop known plugin namespace prefixes so invoked names match the registry
    (registry entries are bare dir/file stems). `dev-team:plan` -> `plan`;
    `agentic-dev-team:plan` -> `plan`; other names pass through."""
    for prefix in ("agentic-dev-team:", "dev-team:"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name'''

if old not in src:
    print(f"ERROR: expected _strip_ns body not found in {path}", file=sys.stderr)
    sys.exit(1)
with open(path, "w") as f:
    f.write(src.replace(old, new, 1))
print(f"patched {path}")
PY
      applied "updated _strip_ns() in $EXTRACT"
    fi
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE B — Changes that require /agent-eval validation before applying
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo -e "${BOLD}── Phase B: Requires /agent-eval validation before applying ──${RESET}"

# ─────────────────────────────────────────────────────────────────────────────
header "Validate new hooks with /agent-eval (before shipping)"
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  manual "Run the following after Phase A changes are committed to a branch:
    /agent-eval --target hooks/verify-guard.sh --k 3
    /agent-eval --target hooks/bash-retry-guard.sh --k 3
  Acceptance: false-positive rate <10% (hook fires on non-spinning sessions).
  Only ship to main after both pass."
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Evaluate 5 model tier downband candidates"
# Agents: security-review, domain-review, test-smell-review, naming-review, complexity-review
# Rationale: pattern-match workloads may not require high/medium effort tier.
# Do NOT change effort: bands until eval confirms accuracy is maintained at k≥3.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  manual "Run these evals at k≥3 (requires 29% flakiness resolved first — see step 3):
    /agent-eval --target agents/security-review.md --k 3
    /agent-eval --target agents/domain-review.md --k 3
    /agent-eval --target agents/test-smell-review.md --k 3
    /agent-eval --target agents/naming-review.md --k 3
    /agent-eval --target agents/complexity-review.md --k 3
  If mean_pass@k drops <5pp from current baseline: change 'effort: high' -> 'effort: medium'
  or 'effort: medium' -> 'effort: low' in the respective .md frontmatter.
  Commit each change separately for rollback granularity."
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Resolve eval flakiness (29.2% of pairs non-deterministic at k=3)"
# Block on model tier changes until this is resolved.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  manual "Run full eval suite at k=3 to identify which agents are flaky:
    /agent-eval --all --k 3
  For each flaky agent:
    1. Add a structured output schema to its verdict (JSON with 'verdict', 'confidence', 'findings[]')
    2. Tighten the 'Output format' section to require a definitive pass/fail, not hedging prose
    3. Re-run /agent-eval --target <agent> --k 3 to confirm variance drops
  Target: flaky_count ≤ 3/65 pairs before acting on model tier changes."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE C — Skill / agent text changes (low mechanical risk, apply directly)
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo -e "${BOLD}── Phase C: Skill and orchestrator text changes ──${RESET}"

# ─────────────────────────────────────────────────────────────────────────────
header "Add gate-bypass instruction rule to pr and build skills"
# Source: session-review finding #3. Gate bypass sessions average 74.0 rework
# vs 29.8 gated (2.5× ratio). Add explicit rule to both skills.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  for skill_path in "$PLUGIN_DIR/skills/pr/SKILL.md" "$PLUGIN_DIR/skills/build/SKILL.md"; do
    if [ ! -f "$skill_path" ]; then
      echo -e "  ${YELLOW}SKIP${RESET} — $skill_path not found"
      continue
    fi
    if grep -q "gate.*bypass\|bypass.*gate\|no-verify\|--no-verify" "$skill_path"; then
      skip_step "gate-bypass rule already present in $skill_path"
      continue
    fi
    if $DRY_RUN; then
      echo -e "  ${YELLOW}[DRY RUN]${RESET} would prepend gate-bypass rule to $skill_path"
    else
      python3 - "$skill_path" << 'PY'
import sys
path = sys.argv[1]
with open(path) as f:
    src = f.read()

rule = """## Gate-Bypass Policy

**Never bypass the pre-commit review gate** (`--no-verify` or `-n` on `git commit`).
Sessions that bypass the gate average 2.5× more rework than gated sessions (74.0 vs 29.8
mean rework events). If the gate blocks, investigate and fix the underlying issue rather
than skipping the gate. Gate bypass requires explicit human approval.

"""

# Insert after the first heading line
lines = src.split("\n")
for i, line in enumerate(lines):
    if line.startswith("# "):
        lines.insert(i + 1, "")
        lines.insert(i + 2, rule.rstrip())
        lines.insert(i + 3, "")
        break

with open(path, "w") as f:
    f.write("\n".join(lines))
PY
      applied "added gate-bypass rule to $skill_path"
    fi
  done
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Add stale-spec detection to specs skill"
# Source: session-review tier-2 finding. The specs skill does not detect an
# existing spec's format version; user had to flag stale output manually.
# Add a Step 0 check that compares the existing spec's schema/version marker
# against the current skill's expected format and prompts if they differ.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  SPECS_SKILL="$PLUGIN_DIR/skills/specs/SKILL.md"
  if [ ! -f "$SPECS_SKILL" ]; then
    skip_step "$SPECS_SKILL not found"
  elif grep -q "stale\|format.*version\|version.*check\|existing.*spec" "$SPECS_SKILL"; then
    skip_step "stale-spec detection already present in $SPECS_SKILL"
  else
    if $DRY_RUN; then
      echo -e "  ${YELLOW}[DRY RUN]${RESET} would add Step 0 stale-spec detection to $SPECS_SKILL"
    else
      python3 - "$SPECS_SKILL" << 'PY'
import sys, re
path = sys.argv[1]
with open(path) as f:
    src = f.read()

check_block = """## Step 0 — Existing-spec version check

Before drafting or updating a spec, check whether a spec file already exists for
this feature:

- If no spec file exists: proceed directly to Step 1.
- If a spec file exists: read its opening lines and check for a `<!-- spec-version: -->` comment or a `**Format:**` header field.
  - If the marker is absent or predates the current skill version (see frontmatter `version:`): surface this to the user — *"An existing spec was found but appears to use an older format. Regenerate from scratch, or confirm you want to update in place?"* — and wait for explicit direction before proceeding.
  - If the marker matches the current version: proceed to Step 1 with the existing file as base.

This prevents silently overwriting a current spec and catches format drift before
the plan phase consumes stale artifacts.

"""

# Insert before "## Step 1" (or the first step heading)
match = re.search(r'^(##\s+Step 1\b)', src, re.MULTILINE)
if match:
    insert_at = match.start()
    src = src[:insert_at] + check_block + src[insert_at:]
else:
    # Fallback: append after first heading
    lines = src.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines.insert(i + 2, check_block.rstrip())
            break
    src = "\n".join(lines)

with open(path, "w") as f:
    f.write(src)
PY
      applied "added Step 0 stale-spec detection to $SPECS_SKILL"
    fi
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Wire progress-guardian to build skill dispatch"
# Source: harness-audit §orchestration. progress-guardian (plan adherence, scope
# creep) has 0 invocations across 268 sessions. It should fire at build checkpoints.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  BUILD_SKILL="$PLUGIN_DIR/skills/build/SKILL.md"
  if [ ! -f "$BUILD_SKILL" ]; then
    skip_step "$BUILD_SKILL not found"
  elif grep -q "progress.guardian\|progress_guardian" "$BUILD_SKILL"; then
    skip_step "progress-guardian already referenced in $BUILD_SKILL"
  else
    if $DRY_RUN; then
      echo -e "  ${YELLOW}[DRY RUN]${RESET} would add progress-guardian dispatch note to $BUILD_SKILL"
    else
      python3 - "$BUILD_SKILL" << 'PY'
import sys, re
path = sys.argv[1]
with open(path) as f:
    src = f.read()

guardian_note = """## Scope adherence gate (progress-guardian)

At each slice boundary (before committing a completed step), dispatch the
`progress-guardian` agent to verify:

1. The implementation matches the plan step's scope — no undeclared additions.
2. Commit messages reference the plan step number.
3. No plan steps were silently skipped.

If `progress-guardian` flags scope creep or a missing commit, pause and surface
the discrepancy to the user before proceeding to the next step.

"""

# Insert before the first ## Step heading or ## Phase heading
match = re.search(r'^(##\s+(Step|Phase)\s+\d)', src, re.MULTILINE)
if match:
    insert_at = match.start()
    src = src[:insert_at] + guardian_note + src[insert_at:]
else:
    lines = src.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines.insert(i + 2, guardian_note.rstrip())
            break
    src = "\n".join(lines)

with open(path, "w") as f:
    f.write(src)
PY
      applied "added progress-guardian dispatch gate to $BUILD_SKILL"
    fi
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Add pre-built metrics logging to build skill (enable task-log + review-value)"
# Source: harness-audit §data-gaps. Without task-log and review-value.jsonl,
# per-agent finding rates and inline-checkpoint ROI cannot be computed.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  BUILD_SKILL="$PLUGIN_DIR/skills/build/SKILL.md"
  if [ ! -f "$BUILD_SKILL" ]; then
    skip_step "$BUILD_SKILL not found"
  elif grep -q "review-value\|task.log\|metrics.*log" "$BUILD_SKILL"; then
    skip_step "metrics logging already referenced in $BUILD_SKILL"
  else
    manual "Metrics logging requires a design decision on the review-value schema.
  See docs/eval-system.md for the checkpoint schema.
  Once the schema is agreed, add a 'Metrics emission' section to $BUILD_SKILL
  that appends a record to metrics/review-value.jsonl after each inline checkpoint.
  Fields required: checkpoint, agents_run[], outcome (no-op|fixed|escalated),
  issues_found, issues_fixed, fix_iterations."
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE D — External plugins (writing-team) — file issues, no auto-apply
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo -e "${BOLD}── Phase D: External plugin issues (writing-team) ──${RESET}"

# ─────────────────────────────────────────────────────────────────────────────
header "Scope pre-publish.sh to prose directories (writing-team plugin)"
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  manual "pre-publish.sh lives in the writing-team plugin (not this repo).
  File an issue against the writing-team plugin requesting a guard that exits
  early when the working directory does not contain a 'drafts/' folder.
  Suggested guard (top of pre-publish.sh, after consuming stdin):
    [ -d \"\$PROJECT_DIR/drafts\" ] || exit 0
  This prevents the hook from firing in dev-team workflow sessions where no
  prose draft lifecycle is active."
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Fix post-markdownlint.sh exit behavior (writing-team plugin)"
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  manual "post-markdownlint.sh lives in the writing-team plugin (not this repo).
  The hook currently calls 'markdownlint-cli2 --fix' and always exits 0, even
  when lint errors remain after auto-fix. File an issue requesting:
    1. After --fix, re-run markdownlint-cli2 without --fix to count residual errors.
    2. If residual errors > 0, emit a warning summary (do NOT exit non-zero —
       that would block all writes; advisory output is sufficient).
  This surfaces unfixable lint errors so agents act on them rather than proceeding
  silently."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE E — Manual investigation (requires human judgment)
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo -e "${BOLD}── Phase E: Manual investigation ──${RESET}"

# ─────────────────────────────────────────────────────────────────────────────
header "Audit dispatch paths for codebase-recon and security-engineer"
# Both are effort: high with 0 invocations across 268 sessions.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  manual "Read agents/orchestrator.md and search for 'codebase-recon' and 'security-engineer'.
  If neither appears in the routing table's dispatch conditions:
    Option A: Add a trigger — e.g. dispatch codebase-recon at the start of every
              /plan run on a project with no existing RECON artifact.
    Option B: If no meaningful trigger exists, downband effort: high -> effort: medium
              so they don't carry high-tier cost when eventually dispatched.
  Record the decision in an ADR if it changes a routing contract."
fi

# ─────────────────────────────────────────────────────────────────────────────
header "Wire context-loading-protocol and feedback-learning to orchestrator triggers"
# Source: harness-audit §orchestration. Both are load-bearing orchestration skills
# with 0 invocations across 268 sessions.
# ─────────────────────────────────────────────────────────────────────────────
if should_run; then
  manual "Read agents/orchestrator.md and skills/context-loading-protocol/SKILL.md.
  Identify the phase transition where context-loading-protocol should fire
  (typically: at session start when a task spans >1 conversation turn).
  Add an explicit dispatch line to the orchestrator's Phase 0 or session-init block.
  Similarly for feedback-learning: it should fire when a user correction turn is
  detected. Check whether the orchestrator's correction-handling logic references it;
  if not, add: 'On user correction: invoke feedback-learning to capture the category
  and update the relevant instruction rule.'"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo -e "${BOLD}── Summary ──${RESET}"
echo "  Applied:  $step_applied"
echo "  Skipped:  $step_skipped (already done)"
echo "  Manual:   $step_manual (instructions printed above)"
echo
echo "Next: commit Phase A changes to a feature branch, then run Phase B evals."
echo "Report: reports/harness-audit-2026-06-23.md"
