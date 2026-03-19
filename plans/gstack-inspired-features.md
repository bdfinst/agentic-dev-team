# Plan: Browser QA, Destructive Command Guardrails, Self-Upgrade

**Created**: 2026-03-19
**Branch**: paulh
**Status**: approved

## Goal

Add three capabilities inspired by gstack: (1) browser-based QA for visual verification and interactive testing, (2) destructive command guardrails with careful/freeze/guard modes, and (3) a self-upgrade command for in-session plugin updates. These close the biggest capability gaps identified in the gstack comparison without compromising the quality-first philosophy.

## Acceptance Criteria

- [ ] `/browse` command launches Playwright, navigates to URLs, takes screenshots, clicks elements, and fills forms
- [ ] QA Engineer agent documentation references browser capabilities for e2e visual verification
- [ ] `pre-tool-guard.sh` detects and warns on destructive Bash commands (rm -rf, DROP TABLE, git push --force, git reset --hard, etc.)
- [ ] `/freeze <glob>` restricts Write/Edit to files matching the glob; `/unfreeze` lifts restriction
- [ ] `/guard` activates both careful mode and freeze mode together
- [ ] `/upgrade` detects plugin install location, pulls latest, shows diff, and applies update
- [ ] All new hooks have corresponding eval fixtures in `evals/`
- [ ] `knowledge/agent-registry.md` updated with new commands and token budgets
- [ ] `CLAUDE.md` slash commands table updated

---

## Feature 1: Browser-Based QA

### Step 1: Create `/browse` command

**RED**: Create eval fixture `evals/browse/missing-command.md` — invoke `/browse` and verify it exists with expected argument parsing.
**GREEN**: Create `commands/browse.md` with:
- Frontmatter: `name: browse`, `allowed-tools: Read, Bash(npx playwright *), Bash(node *)`, `user-invocable: true`
- Arguments: `<url> [--screenshot <path>] [--click <selector>] [--fill <selector> <value>] [--wait <ms>] [--viewport <width>x<height>]`
- Procedure: Launch headless Chromium via Playwright, execute action sequence, capture screenshot, return results
- Dependency check: Verify Playwright is available, prompt to install if missing (`npx playwright install chromium`)
- Screenshot output defaults to `tmp/screenshots/<timestamp>.png`
- Claude reads the screenshot via the Read tool (multimodal) and describes what it sees
**REFACTOR**: None needed.
**Files**: `commands/browse.md`, `evals/browse/missing-command.md`
**Commit**: `Add /browse command for browser-based QA interaction`

### Step 2: Create browser interaction skill

**RED**: Create eval fixture that verifies the skill is referenced correctly by the browse command.
**GREEN**: Create `skills/browser-testing.md` with:
- Common interaction patterns (navigation, form fill, click, wait for selector, screenshot)
- Playwright snippet templates that the agent pastes into Bash calls
- Error handling patterns (timeout, element not found, navigation failure)
- Screenshot comparison guidance (describe what you see, compare to expected)
- CAPTCHA/auth handoff protocol: if blocked, instruct user to complete manually then resume
**REFACTOR**: None needed.
**Files**: `skills/browser-testing.md`
**Commit**: `Add browser-testing skill with interaction patterns and templates`

### Step 3: Update QA Engineer agent with browser capabilities

**RED**: Verify QA agent currently has no browser testing references.
**GREEN**: Add to `agents/qa-engineer.md`:
- New responsibility: "Visual verification and browser-based e2e testing"
- New skill reference: `browser-testing`
- New collaboration note: "Uses `/browse` for visual regression and interactive testing when e2e verification is needed"
- Add `Bash(npx playwright *)` to tools list
**REFACTOR**: None needed.
**Files**: `agents/qa-engineer.md`
**Commit**: `Update QA Engineer agent with browser-based testing capabilities`

### Step 4: Register in agent registry and CLAUDE.md

**RED**: Verify `/browse` is not in the registry or CLAUDE.md command table.
**GREEN**:
- Add `/browse` to `knowledge/agent-registry.md` under skills section
- Add row to CLAUDE.md slash commands table
- Add `browser-testing` to skills list in CLAUDE.md quick reference
**REFACTOR**: None needed.
**Files**: `knowledge/agent-registry.md`, `CLAUDE.md`
**Commit**: `Register /browse command and browser-testing skill in docs`

---

## Feature 2: Destructive Command Guardrails

### Step 5: Extend pre-tool-guard for Bash destructive commands

**RED**: Create eval fixture `evals/guards/destructive-bash-undetected.md` — a Bash call with `rm -rf /` should trigger a warning.
**GREEN**: Create `hooks/destructive-guard.sh`:
- New PreToolUse hook that matches `Bash` tool calls (not Write/Edit — those are handled by existing guard)
- Reads `hooks/destructive-commands.json` for patterns
- Pattern categories:
  - **File destruction**: `rm -rf`, `rm -r`, `> /dev/null` redirects on important files
  - **Database destruction**: `DROP TABLE`, `DROP DATABASE`, `TRUNCATE`, `DELETE FROM` (without WHERE)
  - **Git destruction**: `git push --force`, `git push -f`, `git reset --hard`, `git clean -f`, `git checkout -- .`, `git branch -D`
  - **Process destruction**: `kill -9`, `killall`, `pkill`
  - **Permission escalation**: `chmod 777`, `chown`
- Exit 0 with WARNING message (not blocking — user may intend these)
- Message format: "CAUTION: Destructive command detected: `<command>`. This action is hard to reverse. Confirm with the user before proceeding."
**REFACTOR**: Extract shared helpers (JSON loading, pattern matching) into `hooks/lib/guard-utils.sh` if duplication with pre-tool-guard.sh is significant.
**Files**: `hooks/destructive-guard.sh`, `hooks/destructive-commands.json`, `evals/guards/destructive-bash-undetected.md`
**Commit**: `Add destructive command detection hook for Bash tool calls`

### Step 6: Register destructive guard hook in settings

**RED**: Verify the hook is not registered yet.
**GREEN**: Add to `.claude/settings.json` under `hooks.PreToolUse`:
```json
{
  "matcher": "Bash",
  "hooks": [
    { "type": "command", "command": "bash hooks/destructive-guard.sh" }
  ]
}
```
**REFACTOR**: None needed.
**Files**: `.claude/settings.json`
**Commit**: `Register destructive-guard hook in settings.json`

### Step 7: Create `/freeze` and `/unfreeze` commands

**RED**: Create eval fixture verifying freeze state file is created and respected.
**GREEN**:
- Create `commands/freeze.md`:
  - Arguments: `<glob-pattern>` (e.g., `src/auth/**`)
  - Writes freeze state to `hooks/freeze-state.json`: `{"active": true, "allowed_patterns": ["src/auth/**"], "frozen_at": "<timestamp>"}`
  - Displays confirmation: "Scope locked to `<pattern>`. Only matching files can be edited. Use `/unfreeze` to lift."
- Create `commands/unfreeze.md`:
  - Removes `hooks/freeze-state.json`
  - Displays confirmation: "Scope lock lifted. All files are editable."
- Extend `hooks/pre-tool-guard.sh` to also check `hooks/freeze-state.json`:
  - If freeze-state.json exists and `active: true`, block Write/Edit to files that do NOT match `allowed_patterns`
  - Message: "BLOCKED: Freeze mode is active. Only files matching `<pattern>` can be edited. Use `/unfreeze` to lift."
**REFACTOR**: None needed.
**Files**: `commands/freeze.md`, `commands/unfreeze.md`, `hooks/pre-tool-guard.sh`
**Commit**: `Add /freeze and /unfreeze commands for scope-locked editing`

### Step 8: Create `/careful` and `/guard` commands

**RED**: Create eval fixture verifying careful mode toggles destructive guard behavior.
**GREEN**:
- Create `commands/careful.md`:
  - Toggle command — `/careful` enables, `/careful off` disables
  - Writes state to `hooks/careful-state.json`: `{"active": true, "enabled_at": "<timestamp>"}`
  - When active, destructive-guard.sh escalates from WARNING to BLOCK (exit 2 instead of exit 0)
  - Displays: "Careful mode ON. Destructive commands will be blocked until `/careful off`."
- Create `commands/guard.md`:
  - Arguments: `<glob-pattern>`
  - Activates both careful mode AND freeze mode in one command
  - Equivalent to `/careful` + `/freeze <pattern>`
  - Displays: "Guard mode ON. Destructive commands blocked + scope locked to `<pattern>`."
- Update `hooks/destructive-guard.sh` to read `hooks/careful-state.json` — if active, exit 2 instead of exit 0
**REFACTOR**: None needed.
**Files**: `commands/careful.md`, `commands/guard.md`, `hooks/destructive-guard.sh`, `hooks/careful-state.json`
**Commit**: `Add /careful and /guard commands for production safety modes`

### Step 9: Register guardrail commands in docs

**RED**: Verify new commands are not in registry.
**GREEN**: Update `knowledge/agent-registry.md`, CLAUDE.md slash commands table, and CLAUDE.md quick reference with all four new commands (`/freeze`, `/unfreeze`, `/careful`, `/guard`).
**REFACTOR**: None needed.
**Files**: `knowledge/agent-registry.md`, `CLAUDE.md`
**Commit**: `Register guardrail commands in agent registry and CLAUDE.md`

---

## Feature 3: Self-Upgrade

### Step 10: Create `/upgrade` command

**RED**: Create eval fixture verifying upgrade command detects plugin location.
**GREEN**: Create `commands/upgrade.md`:
- Frontmatter: `name: upgrade`, `allowed-tools: Read, Bash(git *), Bash(gh *), Glob, Grep`, `user-invocable: true`
- Procedure:
  1. **Detect install location**: Check if running from:
     - Git repo (development): `git -C <plugin-dir> rev-parse --is-inside-work-tree`
     - Installed plugin: Check `~/.claude/plugins/` or project `.claude/plugins/`
  2. **Check for updates**: `git fetch origin && git log HEAD..origin/main --oneline`
  3. **Show diff**: `git diff HEAD..origin/main --stat` + summary of what changed
  4. **Categorize changes**: Group by agents/skills/commands/hooks modified
  5. **Confirm with user**: "These changes will be applied. Proceed?"
  6. **Apply**: `git pull origin main`
  7. **Post-upgrade**: Show changelog summary, note any new commands or breaking changes
- Edge cases:
  - If no updates available: "Already up to date."
  - If local modifications exist: Warn and suggest stash or manual merge
  - If not a git repo (vendored copy): Suggest re-clone or manual update
**REFACTOR**: None needed.
**Files**: `commands/upgrade.md`, `evals/upgrade/`
**Commit**: `Add /upgrade command for in-session plugin updates`

### Step 11: Register upgrade command in docs

**RED**: Verify `/upgrade` not in registry.
**GREEN**: Update `knowledge/agent-registry.md` and CLAUDE.md with `/upgrade` entry.
**REFACTOR**: None needed.
**Files**: `knowledge/agent-registry.md`, `CLAUDE.md`
**Commit**: `Register /upgrade command in docs`

---

## Pre-PR Quality Gate

- [ ] All eval fixtures pass
- [ ] `/agent-audit` passes (structural compliance)
- [ ] `/code-review --changed` passes
- [ ] CLAUDE.md token budgets updated
- [ ] No secrets or credentials in committed files

## Risks & Open Questions

1. **Playwright dependency**: `/browse` requires Playwright installed in the target project. Should we bundle it or require users to install it? **Mitigation**: Command checks for availability and prompts install on first use (`npx playwright install chromium`). Playwright manages its own browser binaries, so no system-level Chrome install needed.
2. **Freeze state persistence**: `freeze-state.json` persists across sessions. If a session crashes mid-freeze, files stay locked. **Mitigation**: `/unfreeze` is simple; also add a note in `/continue` to check for stale freeze state.
3. **Destructive pattern false positives**: `rm -rf node_modules` is routine, not dangerous. **Mitigation**: Allow-list common safe patterns in `destructive-commands.json`. Start with warnings (not blocks) by default; `/careful` escalates to blocks.
4. **Upgrade in vendored installs**: If the plugin was copied (not cloned), git-based upgrade won't work. **Mitigation**: Detect and suggest re-clone.
5. **Hook ordering**: New destructive-guard hook runs on Bash calls while existing pre-tool-guard runs on Write/Edit. They don't conflict, but document the distinction.
