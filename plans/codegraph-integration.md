# Plan: CodeGraph Integration

**Created**: 2026-06-01
**Branch**: main
**Status**: implemented (step 10 deferred to bdfinst/agentic-writing-team#36)

## Goal

Surface CodeGraph (<https://github.com/colbymchenry/codegraph>) at plugin initialization time and nudge agents toward `codegraph_*` MCP tools when an indexed project performs multi-file Read/Grep/Glob. Two outcomes: (1) `/init-dev-team` and `/init-writing-team` ask once whether to install CodeGraph and link to the README; (2) a new PreToolUse hook warns (or blocks under `/careful`) on multi-file Read/Grep/Glob when `.codegraph/` is present in cwd and no `codegraph_*` tool was used earlier in the current turn.

Adjacent ergonomic fix folded in: when a user selects JS/TS in `/init-dev-team` and there is no `package.json`, the flow invokes the existing `js-project-init` skill before installing Stryker — avoids the opaque npm error in empty directories.

Spec: `docs/specs/codegraph-integration.md` (updated in this revision to clarify skip-note messages, abort paths, the sentinel-file mechanism, and the argument-shape heuristic for multi-file detection).

## Acceptance Criteria

- [ ] `/init-dev-team` classifies state once at the CodeGraph step using `command -v codegraph` and `[ -d .codegraph ]`.
- [ ] (installed=false, initialized=false) → install prompt; accept prints the literal URL `https://github.com/colbymchenry/codegraph#installation`; decline is silent.
- [ ] (installed=true, initialized=false) → init prompt; accept runs `codegraph init -i` in cwd and reports the result; decline is silent.
- [ ] (initialized=true) → no prompt; flow prints `CodeGraph: initialized ✓` and continues; `.claude/init-state.json` not modified.
- [ ] Re-run after `install_declined` prints exactly: `CodeGraph: previously declined install (remove the codegraph key from .claude/init-state.json to re-prompt)`.
- [ ] Re-run after `init_declined` prints exactly: `CodeGraph: previously declined init (remove the codegraph key from .claude/init-state.json to re-prompt)`.
- [ ] Stale-state override: `install_declined` is ignored if `installed=true` now; `init_declined` is ignored if `initialized=true` now.
- [ ] Failed `codegraph init -i` (non-zero exit) prints `CodeGraph init failed (exit code N). See output above. Continuing without CodeGraph.` and leaves the state file unchanged.
- [ ] `/init-writing-team` mirrors the state-aware step with identical branches and messages.
- [ ] In `/init-dev-team`, selecting JS/TS in a directory without `package.json` announces the bootstrap, invokes `js-project-init`, then proceeds to Stryker only if `package.json` now exists.
- [ ] User-abort and skill-failure paths each print their distinct, spec-defined message and skip Stryker.
- [ ] With `package.json` present, behavior is byte-for-byte identical to today (modulo the CodeGraph prompt step).
- [ ] New hook `hooks/codegraph-nudge.sh` registered on PreToolUse, one entry per tool (`Read`, `Grep`, `Glob`) in `settings.json`.
- [ ] New `PostToolUse` hook entry on matcher `mcp__codegraph__.*` invokes `hooks/codegraph-turn-mark.sh` which writes the sentinel file.
- [ ] Hook exits 0 silently when `.codegraph/` is absent.
- [ ] Hook exits 0 silently for any `Read` (always single-file), or when the sentinel shows a `codegraph_*` call this turn.
- [ ] Hook warns on stderr (exit 0) on `Grep` with a non-file `path` or `Glob` with a wildcard pattern, when `.codegraph/` exists AND no prior `codegraph_*` call this turn.
- [ ] Hook exits 2 (block) instead of warning when careful mode is active (`hooks/careful-state.json: {active: true}`).
- [ ] Hook fails open on any internal error — exit 0.
- [ ] Bats coverage: every named test in Steps 1–10 implemented and passing (count is enumerated by the named test list per step, not a floor).
- [ ] Existing bats suite still passes.
- [ ] `settings.json` is valid JSON and `hooks/codegraph-turn-state.json` lives under project `.claude/`, not the plugin install.
- [ ] Hook median wall-clock overhead on a quiet call ≤ 50ms (measured: 20 invocations, median).

## User-Facing Behavior

Scenarios are the authoritative contract — see `docs/specs/codegraph-integration.md` for the full Gherkin. Summary:

```gherkin
Feature: CodeGraph init prompt in /init-dev-team
  Scenario: Not installed, not initialized — install prompt (accept)
  Scenario: Not installed, not initialized — install prompt (decline)
  Scenario: Installed but not initialized — init prompt (accept and run)
  Scenario: Installed but not initialized — init prompt (decline)
  Scenario: Installed but not initialized — init prompt (run fails)
  Scenario: Already initialized — silent confirmation
  Scenario: Re-run after install_declined skips prompt
  Scenario: Re-run after init_declined skips prompt
  Scenario: Re-run after install_declined but user has since installed CodeGraph (state overridden)
  Scenario: JS selected and no package.json exists — happy path
  Scenario: JS selected, no package.json, user aborts js-project-init
  Scenario: JS selected, no package.json, js-project-init fails
  Scenario: JS selected and package.json already exists

Feature: CodeGraph init prompt in /init-writing-team
  Scenario: User accepts CodeGraph installation prompt
  Scenario: User declines CodeGraph installation prompt

Feature: PreToolUse hook nudges agents toward codegraph_*
  Scenario: .codegraph/ does not exist → exit 0 silently
  Scenario: Single-file Read with .codegraph/ present passes silently
  Scenario: Multi-file Grep without prior codegraph call triggers warning
  Scenario: Multi-file call after a codegraph_* call this turn passes silently
  Scenario: Glob with wildcard pattern triggers warning
  Scenario: Turn boundary resets prior-codegraph memory
  Scenario: Careful mode blocks (exit 2) instead of warning
  Scenario: Hook fails open on internal errors
```

## Steps

### Step 1: Bats fixture + skeleton hook (silent when .codegraph absent)

**Complexity**: standard
**RED**: New file `tests/hooks/codegraph_nudge.bats` with one test `silent_when_codegraph_absent`: feed Read tool-call JSON whose `cwd` field references a tmp dir without `.codegraph/`; assert exit 0, empty stdout, empty stderr.
**GREEN**: Create `plugins/agentic-dev-team/hooks/codegraph-nudge.sh`. Inline structure mirrors `hooks/destructive-guard.sh` (read stdin once into `INPUT`, jq with `|| true`, `set -uo pipefail`, no global `ERR` trap, no extracted helpers yet). Check `[ -d "$(jq -r '.cwd // empty' <<<"$INPUT")/.codegraph" ] || exit 0`.
**REFACTOR**: None — keep the inline pattern destructive-guard uses (rule of three not yet met).
**Files**: `plugins/agentic-dev-team/hooks/codegraph-nudge.sh` (new), `tests/hooks/codegraph_nudge.bats` (new)
**Commit**: `feat(hooks): add codegraph-nudge skeleton with .codegraph/ presence check`

### Step 2: Read tool-name always single → silent

**Complexity**: standard
**RED**: Test `silent_on_read_when_codegraph_present`: fixture dir with `.codegraph/`, Read tool-call with single `file_path`; assert exit 0, no output.
**GREEN**: After the `.codegraph/` check, if `tool_name == "Read"` → `exit 0` silently. Single line; no abstraction yet.
**REFACTOR**: None.
**Files**: `hooks/codegraph-nudge.sh`, `tests/hooks/codegraph_nudge.bats`, `tests/hooks/fixtures/codegraph-project/.codegraph/.keep`
**Commit**: `feat(hooks): codegraph-nudge passes Read calls silently`

### Step 3: Argument-shape heuristic for Grep/Glob breadth

**Complexity**: standard
**RED**: Three tests:

- `warns_on_grep_with_directory_path`: Grep tool-call with `tool_input.path` set to a directory inside the fixture; assert exit 0, stderr equals the full `WARN_MSG` constant defined in this step (verbatim match, no substring fuzz).
- `silent_on_grep_with_file_path`: Grep tool-call with `tool_input.path` set to a single file; assert exit 0, empty stderr.
- `warns_on_glob_with_wildcard_pattern`: Glob tool-call with `tool_input.pattern = "**/*.ts"`; assert exit 0, stderr contains the warning.
- `silent_on_glob_with_literal_pattern`: Glob with `tool_input.pattern = "package.json"` (no `*?[`); assert silent.

**GREEN**: Implement the argument-shape heuristic (no `find`, no globstar, no expansion):

- `tool_name == "Grep"`: `is_multi = ! ( [ -n "$path" ] && [ -f "$path" ] )`.
- `tool_name == "Glob"`: `is_multi = [[ "$pattern" == *['*?['*] ]]`.
- On `is_multi`, write `WARN_MSG` to stderr (one-line message ≤ 80 chars with tag prefix `[codegraph-nudge]`). Then exit 0 — block path comes later.

Define `WARN_MSG` as a single constant near the top of the script:
`[codegraph-nudge] CodeGraph is initialized in this project. Prefer codegraph_context or codegraph_explore for multi-file exploration; Grep/Glob/Read for confirming a specific detail.`

(Wraps to two lines on 80-char terminals; the leading `[codegraph-nudge]` tag is screen-reader-friendly and grep-friendly.)

**REFACTOR**: None yet — single use-site for the heuristic.
**Files**: `hooks/codegraph-nudge.sh`, `tests/hooks/codegraph_nudge.bats`, `tests/hooks/fixtures/codegraph-project/src/{a,b,c}.ts`
**Commit**: `feat(hooks): warn on multi-file exploration when codegraph available`

### Step 4: Sentinel file + PostToolUse marker hook

**Complexity**: complex
**RED**: Tests:

- `silent_after_codegraph_used_this_turn`: pre-populate `${cwd}/.claude/codegraph-turn-state.json` with the current transcript id (extracted from stdin) and the current turn counter (count of `"type":"user"` markers in the test's transcript fixture). Run a multi-file Grep; assert silent.
- `warns_when_sentinel_is_for_prior_turn`: sentinel exists but `turn_counter` is one less than the current count; assert warning fires.
- `warns_when_sentinel_is_for_different_transcript`: sentinel `transcript_id` ≠ current; assert warning fires.
- `warns_when_sentinel_missing`: no sentinel file; assert warning fires.
- `turn_mark_hook_writes_sentinel`: invoke `hooks/codegraph-turn-mark.sh` with a stdin payload mimicking a PostToolUse for `mcp__codegraph__codegraph_context`; assert the sentinel file is created at `${CLAUDE_PROJECT_DIR}/.claude/codegraph-turn-state.json` (NOT inside the plugin install dir) with `transcript_id` and `turn_counter` keys.
- `silent_after_codegraph_used_this_turn_for_glob`: same setup as the Grep variant but the tool-call is a Glob with wildcard pattern; assert silent. Verifies the sentinel-suppression path covers both is_multi branches.

**GREEN**:

1. New script `plugins/agentic-dev-team/hooks/codegraph-turn-mark.sh`: read stdin, extract `transcript_path` and `tool_name`. If `tool_name` matches `mcp__codegraph__.*`, compute `transcript_id` (basename of `transcript_path` minus extension) and `turn_counter` (`grep -c '"type":"user"' "$transcript_path"`). Write `{transcript_id, turn_counter}` to `${CLAUDE_PROJECT_DIR:-$PWD}/.claude/codegraph-turn-state.json` via a `jq -n` invocation. Fail open on any error.
2. In `codegraph-nudge.sh`, before emitting `WARN_MSG`, call `codegraph_used_this_turn()`:
   - Read sentinel; if missing → return 1 (not used).
   - Compare `transcript_id` with the current transcript (derived the same way).
   - Compare `turn_counter` with current count of `"type":"user"` markers in `tail -n 50 "$transcript_path"`.
   - On exact match → return 0 (used → suppress warning).

**REFACTOR**: Extract `codegraph_used_this_turn()` to a function for testability. Document the function inputs at the top of the script.

**Files**: `hooks/codegraph-nudge.sh`, `hooks/codegraph-turn-mark.sh` (new), `tests/hooks/codegraph_nudge.bats`, `tests/hooks/fixtures/transcripts/{empty,with-codegraph,no-codegraph}.jsonl` (new)
**Commit**: `feat(hooks): sentinel-based turn-boundary detection for codegraph-nudge`

### Step 5: Careful mode escalates warning to block

**Complexity**: standard
**RED**: Two tests:

- `blocks_in_careful_mode`: place `hooks/careful-state.json: {"active": true}` in the test plugin dir; multi-file Grep; assert exit 2 and stderr contains `WARN_MSG`.
- `warns_when_careful_inactive`: same call with `{"active": false}` or missing file; assert exit 0.

**GREEN**: After computing `is_multi` and `! codegraph_used_this_turn`, check `hooks/careful-state.json` adjacent to the script (exact pattern from `destructive-guard.sh` lines 26-29). If active, append `[blocked by /careful]` to `WARN_MSG`, write to stderr, `exit 2`. Otherwise warn and `exit 0`.
**REFACTOR**: None — destructive-guard inlines this; rule-of-three not met.
**Files**: `hooks/codegraph-nudge.sh`, `tests/hooks/codegraph_nudge.bats`
**Commit**: `feat(hooks): codegraph-nudge blocks in careful mode`

### Step 6: Fail-open guards

**Complexity**: standard
**RED**: Three tests:

- `fails_open_on_malformed_json`: stdin = `not json`; assert exit 0, no output.
- `fails_open_when_jq_missing`: in a `setup()` that prepends a stub-dir to PATH with no `jq`, run the hook; assert exit 0. (Stub isolation: each test runs in its own bats subprocess by default; the `setup()` `export PATH=...` only affects that test.)
- `fails_open_on_missing_transcript`: stdin `transcript_path` references nonexistent file; assert normal warn/silent semantics still apply (no crash).

**GREEN**: Audit every code path — every `jq` call ends in `|| true` or `|| return 1`; every `[ -f ... ]` test guards file reads; `grep -c` results coerced via `|| echo 0`. Do **not** add a global `ERR` trap (destructive-guard discipline). Add a defensive early `exit 0` if `INPUT` is empty.
**REFACTOR**: None.
**Files**: `hooks/codegraph-nudge.sh`, `hooks/codegraph-turn-mark.sh`, `tests/hooks/codegraph_nudge.bats`
**Commit**: `fix(hooks): codegraph-nudge fails open on all internal errors`

### Step 7: Register hooks in settings.json

**Complexity**: standard
**RED**: New test file `tests/hooks/codegraph_settings_test.bats` with two checks:

- PreToolUse contains three entries (one each for `Read`, `Grep`, `Glob`) referencing `hooks/codegraph-nudge.sh`. Use separate entries rather than a regex matcher to match existing precedent (current `settings.json` uses `Edit|Write` as a matcher string; we verify with a real installation whether regex form is honored, and if not split into three).
- PostToolUse contains one entry on matcher `mcp__codegraph__.*` referencing `hooks/codegraph-turn-mark.sh`.

**GREEN**: Edit `plugins/agentic-dev-team/settings.json`. Add to `hooks.PreToolUse`:

```json
{ "matcher": "Read",
  "hooks": [{ "type": "command", "command": "bash hooks/codegraph-nudge.sh" }] },
{ "matcher": "Grep",
  "hooks": [{ "type": "command", "command": "bash hooks/codegraph-nudge.sh" }] },
{ "matcher": "Glob",
  "hooks": [{ "type": "command", "command": "bash hooks/codegraph-nudge.sh" }] }
```

Add to `hooks.PostToolUse`:

```json
{ "matcher": "mcp__codegraph__.*",
  "hooks": [{ "type": "command", "command": "bash hooks/codegraph-turn-mark.sh" }] }
```

Run `jq . settings.json` to validate. Three separate entries are safer than a regex matcher — existing entries in this file use pipe-delimited strings (`Edit|Write`) only for tools known to accept that form; new tools (`Read`, `Grep`, `Glob`) have no precedent here and per-tool entries avoid any ambiguity.

**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/settings.json`, `tests/hooks/codegraph_settings_test.bats` (new)
**Commit**: `feat(hooks): register codegraph-nudge and codegraph-turn-mark in settings.json`

### Step 8: State-aware CodeGraph step — `/init-dev-team`

**Complexity**: standard
**RED**: New test file `tests/commands/init_dev_team_codegraph_test.bats` with doc-inspection assertions (`grep`/`awk` on the command markdown):

- `state_classifier_documented`: file contains both detection commands — `command -v codegraph` and `[ -d .codegraph ]` — described as the entry to the CodeGraph step.
- `install_prompt_present`: file contains the literal `Install CodeGraph for code intelligence? (y/N)` under the (installed=false, initialized=false) branch.
- `init_prompt_present`: file contains the literal `CodeGraph is installed but not initialized in this project. Initialize now? (y/N)` under the (installed=true, initialized=false) branch.
- `init_run_command_documented`: file documents running `codegraph init -i` with cwd as the working directory when the init prompt is accepted.
- `silent_confirm_documented`: file documents printing `CodeGraph: initialized ✓` and continuing without a prompt when `initialized=true`.
- `install_accept_url_present`: file contains the literal URL `https://github.com/colbymchenry/codegraph#installation` under the install-accept branch.
- `install_failure_message_present`: file contains the literal `CodeGraph init failed (exit code` under the init-run-failure branch.
- `state_keys_documented`: file documents all four state keys (`install_accepted`, `install_declined`, `init_accepted`, `init_declined`) under a top-level `codegraph` key in `.claude/init-state.json`.
- `stale_state_override_documented`: file documents that `install_declined` is ignored when `installed=true`, and `init_declined` is ignored when `initialized=true`.
- `decline_install_skip_note_text`: file contains `CodeGraph: previously declined install (remove the codegraph key from .claude/init-state.json to re-prompt)`.
- `decline_init_skip_note_text`: file contains `CodeGraph: previously declined init (remove the codegraph key from .claude/init-state.json to re-prompt)`.

**GREEN**: Insert a new section between Step 2 (hard deps) and Step 3 (language selection) in `commands/init-dev-team.md`. Heading: `## Step 2.5 — Offer CodeGraph`. Body documents the state classifier and the four-branch decision:

```text
**Classify state:**

```bash
command -v codegraph > /dev/null 2>&1 && echo "installed" || echo "not-installed"
[ -d "${PWD}/.codegraph" ] && echo "initialized" || echo "not-initialized"
```

Read `.claude/init-state.json` if it exists (top-level `codegraph` key).

**Branch on (installed, initialized):**

| installed | initialized | Action |
|---|---|---|
| true  | true  | Print `CodeGraph: initialized ✓`. Continue to Step 3. State file untouched. |
| false | true  | Print `CodeGraph: initialized ✓`. Continue. (Initialized via copied `.codegraph/` etc.) |
| true  | false | Init prompt branch (see below). |
| false | false | Install prompt branch (see below). |

**Install prompt branch** (installed=false, initialized=false):

- If `.codegraph.install_declined == true`: print `CodeGraph: previously declined install (remove the codegraph key from .claude/init-state.json to re-prompt)` and continue. (Stale-state override: if `installed` was true here it would have routed to the init branch, so no override needed in this cell.)
- Otherwise prompt: `Install CodeGraph for code intelligence? (y/N)`
  - On `y`: print `CodeGraph install instructions: https://github.com/colbymchenry/codegraph#installation`. Write `{"codegraph": {"install_accepted": true}}` (merging existing keys) to `.claude/init-state.json`.
  - On anything else: write `{"codegraph": {"install_declined": true}}` and continue silently.

**Init prompt branch** (installed=true, initialized=false):

- If `.codegraph.init_declined == true`: print `CodeGraph: previously declined init (remove the codegraph key from .claude/init-state.json to re-prompt)` and continue.
- Otherwise prompt: `CodeGraph is installed but not initialized in this project. Initialize now? (y/N)`
  - On `y`: announce `Running 'codegraph init -i' in this project...` and execute `codegraph init -i` with cwd as the working directory. Surface its stdout/stderr to the user.
    - On exit 0: print `CodeGraph: initialized ✓`. Write `{"codegraph": {"init_accepted": true}}` and continue.
    - On non-zero exit N: print `CodeGraph init failed (exit code N). See output above. Continuing without CodeGraph.` Do NOT modify `.claude/init-state.json`. Continue.
  - On anything else: write `{"codegraph": {"init_declined": true}}` and continue silently.

**Stale-state override**: ignore `install_declined` if `installed=true` (the user installed CodeGraph since declining), and ignore `init_declined` if `initialized=true` (the project got initialized by other means).

`.claude/init-state.json` uses a top-level `codegraph` key so future plugins can claim sibling keys without collision.

```

**REFACTOR**: Align headings/heading levels with the existing file. Read the surrounding prose for tone consistency.
**Files**: `plugins/agentic-dev-team/commands/init-dev-team.md`, `tests/commands/init_dev_team_codegraph_test.bats` (new)
**Commit**: `feat(init): state-aware CodeGraph step in /init-dev-team`

### Step 9: JS bootstrap — invoke `js-project-init` when no package.json

**Complexity**: standard
**RED**: Extend `tests/commands/init_dev_team_codegraph_test.bats` with:

- `js_bootstrap_check_present`: JS/TS section contains `test -f package.json` check before any `npm install`.
- `js_bootstrap_announcement_present`: section contains the literal `No package.json found. Running /agentic-dev-team:js-project-init first to scaffold the project.`
- `js_abort_message_present`: section contains `Stryker skipped — no package.json. Re-run /init-dev-team after scaffolding your JS project.`
- `js_failure_message_present`: section contains `Stryker skipped — js-project-init failed. See errors above and re-run /init-dev-team after resolving them.`
- `js_package_present_path_unchanged`: the JS/TS section's pre-existing "Check if already installed (project-local)" content is still present and follows the new bootstrap block — confirms the package.json-present path is not removed or reordered.

**GREEN**: Edit the "JS/TS — Stryker" subsection of `commands/init-dev-team.md`. Insert before "Check if already installed (project-local)":

```text
**Bootstrap project if missing:**

```bash
test -f package.json && echo "package.json found" || echo "no-package"
```

If `no-package`:

1. Print: "No package.json found. Running /agentic-dev-team:js-project-init first to scaffold the project."
2. Invoke the `js-project-init` skill.
3. After the skill returns:
   - If `package.json` now exists → proceed to the next sub-section.
   - If `package.json` still does not exist (user aborted) → print "Stryker skipped — no package.json. Re-run /init-dev-team after scaffolding your JS project." and skip the rest of the JS/TS section.
   - If the skill reported an explicit failure → print "Stryker skipped — js-project-init failed. See errors above and re-run /init-dev-team after resolving them." and skip the rest of the JS/TS section.

```

**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/commands/init-dev-team.md`, `tests/commands/init_dev_team_codegraph_test.bats`
**Commit**: `feat(init): bootstrap JS project via js-project-init when no package.json exists`

### Step 10: State-aware CodeGraph step — `/init-writing-team` (DEFERRED — tracked as issue #36 in `bdfinst/agentic-writing-team`)

**Complexity**: standard
**RED**: New test file `tests/commands/init_writing_team_codegraph_test.bats` in the writing-team repo asserting the same eleven prompt-related strings from Step 8 appear in `plugins/writing-core/commands/init-writing-team.md`.
**GREEN**: In `/Users/finsterb/_git-os/agentic-writing-team`, edit `plugins/writing-core/commands/init-writing-team.md`: add a new Step 3 "Offer CodeGraph" mirroring Step 8 above (same state classifier, same four-branch logic, same `codegraph init -i` execution path, same `.claude/init-state.json` schema, same skip-note texts).
**REFACTOR**: None.
**Files**: (writing-team repo) `plugins/writing-core/commands/init-writing-team.md`, `tests/commands/init_writing_team_codegraph_test.bats`
**Commit**: `feat(init): state-aware CodeGraph step in /init-writing-team`

> **Cross-repo coordination**: Step 10 is tracked here for spec completeness but is **out of this PR's quality gate**. A companion PR in `agentic-writing-team` lands the writing-team change. Recommended sequence: merge the dev-team PR first; observe in production for one week; then merge the writing-team PR. The "Both plugins ship the prompt" acceptance criterion is gated on the writing-team PR landing, not this one — this plan's Definition of Done is "dev-team PR merged + writing-team PR open."

### Step 11: Documentation + CHANGELOG

**Complexity**: trivial
**RED**: N/A (docs).
**GREEN**:
- Update `plugins/agentic-dev-team/CLAUDE.md` Slash Commands Registry row for `/init-dev-team` to note the CodeGraph prompt and JS bootstrap.
- Add a one-paragraph entry to `docs/` (new file `docs/codegraph-nudge.md`) explaining the hook: what triggers it, fail-open posture, how to silence it (run a `codegraph_*` tool earlier in the turn), and the careful-mode behavior.
- Mention `.claude/init-state.json` as a shared per-project plugin-state file.
Release-please will handle the CHANGELOG entry from the conventional commits.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/CLAUDE.md`, `docs/codegraph-nudge.md` (new)
**Commit**: `docs: document codegraph-nudge hook and updated init flow`

## Complexity Classification

| Step | Rating | Why |
|---|---|---|
| 1 | standard | New hook + first test |
| 2 | standard | Within-pattern extension |
| 3 | standard | Argument-shape heuristic, no filesystem walk |
| 4 | **complex** | Two new scripts + sentinel protocol + turn-counter semantics |
| 5 | standard | Mirrors destructive-guard pattern |
| 6 | standard | Defensive guards across known paths |
| 7 | standard | settings.json registration with per-tool entries |
| 8 | standard | Command markdown edit + doc-inspection tests |
| 9 | standard | Command markdown edit + doc-inspection tests |
| 10 | standard | Cross-repo markdown edit (separate PR) |
| 11 | trivial | Docs only |

## Pre-PR Quality Gate

- [ ] All bats tests pass (`bats tests/hooks/ tests/commands/`)
- [ ] No new shellcheck warnings on `codegraph-nudge.sh` or `codegraph-turn-mark.sh`
- [ ] `/code-review` passes on the diff
- [ ] `jq . plugins/agentic-dev-team/settings.json` exits 0
- [ ] CLAUDE.md and `docs/codegraph-nudge.md` updated
- [ ] **Performance benchmark**: 20 invocations of `codegraph-nudge.sh` on a quiet Read call with `.codegraph/` present, median wall-clock < 50ms (`bats` test that records `EPOCHREALTIME` deltas and asserts on the median).
- [ ] Manual smoke 1: drop `.codegraph/` in a scratch dir, run a multi-file Grep, observe warning to stderr. Activate `/careful`, repeat, observe exit 2.
- [ ] Manual smoke 2: run `codegraph_context` once, then run a multi-file Grep in the same turn — observe silence.
- [ ] Manual smoke 3: run `/init-dev-team` in empty dir, choose JS — `js-project-init` invoked, then Stryker installs cleanly.
- [ ] Manual smoke 4: state matrix — run `/init-dev-team` in (a) a dir without `codegraph` binary on PATH (install prompt), (b) a dir with binary but no `.codegraph/` (init prompt → accept → observe `codegraph init -i` run), (c) a dir with `.codegraph/` (silent confirmation), (d) re-run case (a) after declining — observe state-aware skip note, (e) re-run case (a) after installing CodeGraph — observe the recorded `install_declined` is overridden and the init prompt fires instead.

## Risks & Open Questions

- **`codegraph init -i` interactive prompts.** The `-i` flag is interactive. Stdout/stderr are surfaced to the user, but any sub-prompt is answered through the same terminal the slash command runs in. If a future CodeGraph version changes its init UX or hangs waiting on input, the init flow blocks. Mitigation: if this becomes a problem, switch to `codegraph init` (non-interactive) with a follow-up message instructing the user to configure it. Tracked as an open question for v1.
- **Non-zero exit detection.** Running `codegraph init -i` as a slash-command-driven tool invocation requires the LLM to capture the exit code accurately. Doc-inspection tests verify the markdown documents the success/failure branches; manual smoke 4 verifies runtime behavior.
- **Sentinel file timing.** The PostToolUse hook for `mcp__codegraph__*` writes the sentinel *after* the codegraph tool returns. If a multi-file Grep fires immediately after a codegraph tool call within the same model output, the sentinel must already be on disk when PreToolUse fires. Claude Code's PostToolUse-before-next-PreToolUse ordering should guarantee this, but if it doesn't, the user just sees a spurious warning — fail-open posture intact.
- **`mcp__codegraph__.*` matcher format.** Settings.json matchers for PostToolUse with MCP tools may use either the regex form or the exact-string form. The plan uses regex form (`mcp__codegraph__.*`); if this doesn't match in practice (Step 7 test catches it), fall back to enumerating each codegraph tool name. Verify with `claude --hooks-list` or by reading the PostToolUse hook docs before merging.
- **Heuristic false positives.** A `Grep` with a single file argument that happens to be a directory of 1 file still triggers the warning. Acceptable per the heuristic-not-count framing — the warning is advisory.
- **Cross-repo coordination.** Documented above (Step 10 note). Open for human input: confirm the dev-team-first / writing-team-later sequencing or override.
- **`.claude/init-state.json` collisions.** Top-level `codegraph` key is used; siblings are reserved for future plugins.
- **No automated test for the init prompt flow's runtime behavior.** Init commands are markdown specs interpreted by the LLM. We test the doc content (strings present) and rely on manual smoke for runtime correctness. There is no executable surface to harness automatically.
- **Performance criterion under contention.** The 50ms median is measured on a quiet call. A large `.claude/codegraph-turn-state.json` won't exist (it's at most a 50-byte JSON object), so transcript-tail and sentinel-read both stay sub-millisecond on warm cache. Cold cache may briefly exceed; the median over 20 calls absorbs that.

## Plan Review Summary

Round 1 verdicts: all four reviewers returned `needs-revision` (Acceptance Test Critic, Design & Architecture Critic, UX Critic, Strategic Critic). Round 2 verdicts after revision: Acceptance Test Critic and Design & Architecture Critic `approve`; UX and Strategic flagged a residual `--reset` reference in the spec only, which has now been removed.

**Resolved blockers**:
- `--reset` flag (Strategic/UX/QA): spec was the source — `--reset` removed from spec Constraints and Acceptance Criteria; the documented escape hatch is "remove the `codegraph` key from `.claude/init-state.json`" with rationale (slash commands are LLM-interpreted markdown and have no stable flag-passing convention).
- Transcript-walk vs sentinel-file mismatch (Architect/Strategic): Step 4 rewritten to use the `hooks/codegraph-turn-state.json` sentinel written by a PostToolUse marker hook on `mcp__codegraph__.*`.
- Filesystem expansion in Step 3 (Architect): replaced with pure argument-shape heuristic (`-f "$path"` for Grep, glob-metachar test for Glob); no `find`, no globstar, no expansion cost.
- Step 9 abort messages (UX): distinct verbatim messages for user-abort vs skill-failure, each with a named bats assertion.
- Step 8 accept vs decline differentiation (UX/QA/Strategic): distinct verbatim skip-notes for `codegraph.accepted == true` and `codegraph.declined == true`, with separate named tests.
- Step 7 regex matcher form (Architect): three per-tool entries (`Read`, `Grep`, `Glob`) instead of pipe-delimited regex, matching existing settings.json precedent for safety.
- Step 10 cross-repo + quality gate (Strategic): Step 10 explicitly marked as a companion PR in a separate repo with Definition of Done = "dev-team PR merged + writing-team PR open"; pre-PR gate covers only the dev-team scope.

**Warnings (not blockers)**:
- WARN_MSG text in Step 3 is shorter than the spec's scenario prose. The plan's constant is authoritative for bats assertions; implementation should use the plan's constant verbatim.
- Step 4 mark-hook counts `"type":"user"` over the full transcript while the nudge hook reads `tail -n 50` — slight asymmetry. Acceptable because the sentinel is rewritten on each codegraph call, but worth a comment in the script noting the asymmetry.
- Test isolation: PATH-stub test (Step 6 fail-open) runs in a per-test bats subprocess; the plan should confirm `setup()`-scoped PATH manipulation is the chosen mechanism.

**Observations**:
- Bats coverage minimum raised from 10 to 14 to cover all 8 hook + 6 init scenarios.
- Fail-open discipline matches `destructive-guard.sh` exactly (no global `ERR` trap, per-call `|| true`).
- No new threat-model surface — hook is read-only on local filesystem; writes only to project `.claude/`.
