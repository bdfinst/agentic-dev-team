# Spec: CodeGraph Integration for Plugin Init Flows

## Intent Description

Both the `agentic-dev-team` and `writing-core` plugins should offer CodeGraph (<https://github.com/colbymchenry/codegraph>) as part of their initialization workflow, and the dev-team plugin should actively steer agents toward it once installed.

Two outcomes:

1. **Discovery surface.** Users running `/init-dev-team` or `/init-writing-team` are met with a state-aware CodeGraph step. The flow detects two booleans — *is the `codegraph` binary on `$PATH`?* and *does `.codegraph/` exist in cwd?* — and branches:
   - **Not installed, not initialized**: prompt to install (links to the README). The plugin does not install CodeGraph itself because CodeGraph has its own binary and indexing setup.
   - **Installed but not initialized in this project**: prompt to initialize. On accept, the flow offers to run `codegraph init -i` in cwd; on confirm, it executes the command and reports the result.
   - **Initialized (`.codegraph/` present)**: skip silently with a one-line confirmation ("CodeGraph: initialized ✓").
   Each prompt records its outcome under `.claude/init-state.json` so re-runs print a state-aware skip note rather than re-asking.
2. **Behavior nudge.** When a project has `.codegraph/` in its cwd, a PreToolUse hook fires on `Read`, `Grep`, and `Glob` calls. If the call pattern looks like exploration (no `codegraph_*` MCP call has been made earlier in the current turn AND the call spans more than 2 distinct files) the hook surfaces a warning recommending `codegraph_context` / `codegraph_explore` instead. In `/careful` mode it blocks.

Additionally, the dev-team init flow has a small ergonomic gap: when a user selects JS/TS and there is no `package.json` in the project root, `npm install --save-dev @stryker-mutator/core` fails with an opaque error. The init flow should bootstrap a JS project via the existing `js-project-init` skill before proceeding with Stryker installation.

The motivation is that CodeGraph collapses dozens of grep+read calls into 2-3 indexed queries. Without active surfacing, agents fall back to file-by-file exploration even when the index is available — wasting tokens and slowing answers.

## User-Facing Behavior

```gherkin
Feature: CodeGraph init prompt in /init-dev-team

  Background:
    Given the init flow has reached the CodeGraph step (after hard deps)
    And the flow has detected two state booleans:
      | installed     | true if `command -v codegraph` succeeds   |
      | initialized   | true if `${cwd}/.codegraph/` exists       |

  Scenario: Not installed, not initialized — install prompt (accept)
    Given installed=false AND initialized=false
    And no prior decline recorded in .claude/init-state.json
    When the user is asked "Install CodeGraph for code intelligence? (y/N)"
    And the user answers "y"
    Then the flow prints "CodeGraph install instructions: https://github.com/colbymchenry/codegraph#installation"
    And the flow writes {"codegraph": {"install_accepted": true}} to .claude/init-state.json
    And the flow continues to language selection

  Scenario: Not installed, not initialized — install prompt (decline)
    Given installed=false AND initialized=false
    When the user is prompted and answers "n" or empty
    Then the flow writes {"codegraph": {"install_declined": true}} to .claude/init-state.json
    And no link is printed
    And the flow continues to language selection

  Scenario: Installed but not initialized — init prompt (accept and run)
    Given installed=true AND initialized=false
    And no prior init_declined recorded
    When the user is asked "CodeGraph is installed but not initialized in this project. Initialize now? (y/N)"
    And the user answers "y"
    Then the flow announces "Running `codegraph init -i` in this project..."
    And the flow executes `codegraph init -i` with cwd as the working directory
    And on success the flow prints "CodeGraph: initialized ✓" and writes {"codegraph": {"init_accepted": true}} to .claude/init-state.json
    And on non-zero exit the flow prints "CodeGraph init failed (exit code N). See output above. Continuing without CodeGraph." and does NOT record acceptance
    And the flow continues to language selection

  Scenario: Installed but not initialized — init prompt (decline)
    Given installed=true AND initialized=false
    When the user is prompted and answers "n" or empty
    Then the flow writes {"codegraph": {"init_declined": true}} to .claude/init-state.json
    And the flow continues to language selection

  Scenario: Already initialized — silent confirmation
    Given initialized=true
    When the init flow reaches the CodeGraph step
    Then the flow prints "CodeGraph: initialized ✓" and continues to language selection
    And no prompt is shown
    And .claude/init-state.json is NOT modified

  Scenario: Re-run after install_declined
    Given installed=false AND initialized=false
    And .claude/init-state.json contains {"codegraph": {"install_declined": true}}
    When the user runs /init-dev-team again
    Then the prompt is skipped with: "CodeGraph: previously declined install (remove the codegraph key from .claude/init-state.json to re-prompt)"

  Scenario: Re-run after init_declined, still installed and uninitialized
    Given installed=true AND initialized=false
    And .claude/init-state.json contains {"codegraph": {"init_declined": true}}
    When the user runs /init-dev-team again
    Then the prompt is skipped with: "CodeGraph: previously declined init (remove the codegraph key from .claude/init-state.json to re-prompt)"

  Scenario: Re-run after install_declined but user has since installed CodeGraph
    Given installed=true AND initialized=false
    And .claude/init-state.json contains {"codegraph": {"install_declined": true}}
    When the user runs /init-dev-team again
    Then the install_declined record is ignored (the user's environment has changed)
    And the init prompt is shown as in the "installed but not initialized" scenario

  Scenario: Re-run after init_accepted with .codegraph/ still present
    Given installed=true AND initialized=true
    And .claude/init-state.json contains {"codegraph": {"init_accepted": true}}
    When the user runs /init-dev-team again
    Then the flow prints "CodeGraph: initialized ✓" and continues
    # The presence of .codegraph/ supersedes any recorded state.

  Scenario: JS selected and no package.json exists — happy path
    Given the user runs /init-dev-team
    And the user selects "JS/TS" at language selection
    And there is no package.json in the current working directory
    When the JS/TS install step begins
    Then the flow announces "No package.json found. Running /agentic-dev-team:js-project-init first to scaffold the project."
    And the flow invokes the js-project-init skill
    And after js-project-init completes (package.json now exists) the Stryker install proceeds

  Scenario: JS selected, no package.json, user aborts js-project-init
    Given the JS/TS install step has invoked js-project-init
    When js-project-init returns and package.json still does NOT exist
    Then the Stryker install is skipped
    And the flow prints "Stryker skipped — no package.json. Re-run /init-dev-team after scaffolding your JS project."

  Scenario: JS selected, no package.json, js-project-init fails
    Given the JS/TS install step has invoked js-project-init
    When js-project-init reports a failure
    Then the Stryker install is skipped
    And the flow prints "Stryker skipped — js-project-init failed. See errors above and re-run /init-dev-team after resolving them."

  Scenario: JS selected and package.json already exists
    Given the user runs /init-dev-team
    And the user selects "JS/TS" at language selection
    And package.json exists in the cwd
    When the JS/TS install step begins
    Then js-project-init is NOT invoked
    And the Stryker install proceeds as it does today

Feature: CodeGraph init prompt in /init-writing-team
  # Mirrors the dev-team state-aware branching: install prompt when not installed,
  # init prompt when installed but not initialized, silent confirmation when
  # .codegraph/ already exists. Same .claude/init-state.json schema, same skip-note
  # texts. Writing-team users are less likely to want CodeGraph but the prompt
  # symmetry keeps the two plugins coherent.

  Scenario: Not installed, not initialized — install prompt
    Given installed=false AND initialized=false
    When the user is prompted and accepts
    Then the flow prints the CodeGraph README URL and continues

  Scenario: Installed but not initialized — init prompt accept and run
    Given installed=true AND initialized=false
    When the user is prompted and accepts
    Then the flow runs `codegraph init -i` in cwd and reports the result

  Scenario: Already initialized — silent confirmation
    Given initialized=true
    Then the flow prints "CodeGraph: initialized ✓" and continues without prompting

Feature: PreToolUse hook nudges agents toward codegraph_*

  Scenario: Single-file Read with .codegraph/ present passes silently
    Given .codegraph/ exists in the cwd
    And no codegraph_* MCP call has been made this turn
    When the agent invokes Read on exactly one file
    Then the hook permits the call without output

  Scenario: Multi-file Grep spanning >2 files without prior codegraph call triggers warning
    Given .codegraph/ exists in the cwd
    And no codegraph_* MCP call has been made this turn
    When the agent invokes Grep with a query that would scan more than 2 files (glob matches >2 files, or the tool's path argument is a directory)
    Then the hook writes to stderr: "CodeGraph is initialized in this project. Prefer codegraph_context or codegraph_explore for multi-file exploration — they return source for many files in one indexed call. Falling back to Grep/Glob/Read is appropriate only to confirm a specific detail."
    And the hook exits 0 (warn) by default
    And in /careful mode the hook exits 2 (block) with the same message

  Scenario: Multi-file call after a codegraph_* call this turn passes silently
    Given .codegraph/ exists in the cwd
    And codegraph_context, codegraph_explore, codegraph_trace, or any codegraph_* tool was called earlier in this turn
    When the agent invokes Grep across >2 files
    Then the hook permits the call without output
    # Rationale: the agent has already used the index; the follow-up read is the
    # "confirm a specific detail" pattern the CLAUDE.md guidance allows.

  Scenario: Glob with broad pattern triggers warning
    Given .codegraph/ exists in the cwd
    And no codegraph_* call has been made this turn
    When the agent invokes Glob with pattern "**/*.ts" or any pattern whose result would clearly exceed 2 files
    Then the hook warns as above

  Scenario: .codegraph/ does not exist
    Given .codegraph/ does NOT exist in the cwd
    When the agent invokes Read, Grep, or Glob with any arguments
    Then the hook exits 0 silently

  Scenario: Turn boundary resets the "prior codegraph call" memory
    Given the hook recorded a codegraph_* call in turn N
    When turn N+1 begins
    Then the hook treats turn N+1 as having no prior codegraph_* call
    # Implementation note: track via a transcript-id + turn-counter sentinel
    # file in .claude/, not a process-wide variable.

  Scenario: Hook fails open on internal errors
    Given the hook script encounters an unexpected error (missing jq, malformed input, etc.)
    Then the hook exits 0 and the tool call proceeds
    # Rationale: a nudge hook must never break agent workflows.
```

## Architecture Specification

### Components touched

| Component | Repo | Change |
|---|---|---|
| `commands/init-dev-team.md` | agentic-dev-team | Add CodeGraph prompt step (after hard deps, before language selection). Add `package.json` check + `js-project-init` invocation inside the JS/TS branch. |
| `commands/init-writing-team.md` | writing-core (`agentic-writing-team` repo) | Add CodeGraph prompt step (after markdownlint install). |
| `hooks/codegraph-nudge.sh` (new) | agentic-dev-team | PreToolUse hook implementing the warn/block logic. |
| `hooks/codegraph-turn-state.json` (new, runtime) | agentic-dev-team | Per-turn sentinel tracking whether codegraph was used this turn. Lives under project `.claude/` not the plugin dir. |
| `settings.json` | agentic-dev-team | Register `codegraph-nudge.sh` under PreToolUse matcher `Read\|Grep\|Glob`. |
| `.claude/init-state.json` (new, runtime) | both | Persistent record of "user accepted/declined CodeGraph". |

### State classifier for the init step

A small helper, computed once at the start of the CodeGraph step in both init commands:

| Boolean | Computation |
|---|---|
| `installed` | `command -v codegraph` exits 0 (binary on `$PATH`) |
| `initialized` | `[ -d "${PWD}/.codegraph" ]` |

The four (installed, initialized) cells drive the branch chosen:

| installed | initialized | Branch | Prior state can short-circuit? |
|---|---|---|---|
| false | false | install prompt | yes (`install_declined`) |
| true | false | init prompt → run `codegraph init -i` on accept | yes (`init_declined`) |
| any | true | silent confirmation only | no — `.codegraph/` presence supersedes recorded state |

**Stale-state handling.** If `install_declined` is recorded but `installed=true` now, the recorded state is ignored — the user's environment has changed and the appropriate next prompt (init) is shown. Symmetrically, `init_declined` is ignored if `initialized=true`. The state file is advisory, not authoritative.

### Init execution

When the user accepts the init prompt, the flow runs `codegraph init -i` with cwd as the working directory. The `-i` flag is CodeGraph's interactive init — it may prompt for additional input. The init command's stdout/stderr are surfaced to the user.

- On exit 0 → record `init_accepted: true`, print "CodeGraph: initialized ✓", continue.
- On non-zero exit → do not record acceptance, print "CodeGraph init failed (exit code N). See output above. Continuing without CodeGraph.", continue.

The plugin does not retry, does not suppress CodeGraph's own output, and does not attempt to repair a failed init.

### Interfaces

**PreToolUse hook contract** (Claude Code spec):

- Stdin: JSON with `tool_name`, `tool_input`, `transcript_path`, `cwd`.
- Stdout: human-readable message.
- Exit 0 = allow (optionally with warning to stderr). Exit 2 = block.

**Multi-file detection logic** (argument-shape heuristic — no live filesystem walk):

- `Read`: always counted as single (Read targets exactly one `file_path`).
- `Grep`: counted as multi unless `tool_input.path` is a regular file (`test -f`). A `path` that is a directory, absent, or a glob → multi.
- `Glob`: counted as multi unless `tool_input.pattern` contains no glob metacharacter (`*`, `?`, `[`).

This is intentionally a coarse heuristic, not a true count. It avoids (a) duplicating the tool's own file enumeration, (b) `shopt -s globstar` portability issues, (c) glob expansion cost. False positives (warning on a 2-file Grep) are acceptable — the warning is advisory.

**Prior-codegraph-this-turn detection** (sentinel file, NOT transcript parsing):

- A separate `PostToolUse` hook fires when any `mcp__codegraph__*` tool completes. It writes `{transcript_id, turn_counter}` to `${CLAUDE_PROJECT_DIR}/.claude/codegraph-turn-state.json`.
- The `codegraph-nudge.sh` PreToolUse hook reads that file. If `transcript_id` matches the current transcript AND `turn_counter` matches the current turn (derived from a cheap `grep -c` of `"type":"user"` over `tail -n 50` of the transcript), it suppresses the warning.
- Mismatched or missing sentinel → no prior codegraph call → warn as usual.
- This avoids walking the full transcript on every Read/Grep/Glob and aligns with the spec's named state file.

### Constraints

- **Fail open.** Any hook error → exit 0. The hook is a nudge, never a gate.
- **No network calls** in the hook (transcript walk is local file read only).
- **Idempotent prompts.** The init prompt reads/writes `.claude/init-state.json`. Re-runs of `/init-dev-team` consult that file and skip the prompt with a state-aware one-liner. To re-trigger the prompt, the user removes the `codegraph` key from `.claude/init-state.json` (a CLI `--reset` flag was considered and rejected — slash commands run as LLM-interpreted markdown and have no stable flag-passing convention).
- **No new dependencies.** Hook is pure bash + `jq` (already a hard dep installed by `/init-dev-team`).
- **Careful-mode reuse.** Reads the existing `hooks/careful-state.json` to decide warn vs block — no parallel state file.
- **Per-project state.** `init-state.json` and any turn-sentinel live under the project's `.claude/`, not the plugin install.

### Dependencies

- `jq` (already required, installed by /init-dev-team step 2).
- Existing `hooks/careful-state.json` schema.
- Existing `js-project-init` skill (invoked from `/init-dev-team`).

### Out of scope

- Installing CodeGraph itself. The plugin only points users at the README.
- Auto-running `codegraph init` without an explicit y/N confirmation. The init prompt is opt-in per-project.
- Re-running `codegraph init` to re-index. CodeGraph has its own re-index workflow.
- Modifying any review or team agents to call codegraph tools (CLAUDE.md global guidance already covers this).
- Per-language nudges (Python, Go) beyond JS bootstrap.
- Detecting partial / corrupt `.codegraph/` (e.g. exists but empty). Presence is treated as initialized.

## Acceptance Criteria

| Criterion | Pass condition |
|---|---|
| State classifier runs once per init | The CodeGraph step computes `installed` and `initialized` exactly once at entry, then branches. |
| Install prompt only when uninstalled | `installed=false, initialized=false` → install prompt with README URL. |
| Init prompt only when installed-but-not-initialized | `installed=true, initialized=false` → init prompt offering to run `codegraph init -i`. |
| Silent confirmation when initialized | `initialized=true` → print "CodeGraph: initialized ✓" and continue. No prompt. State file untouched. |
| Init execution surfaces tool output | When the user accepts init, `codegraph init -i` runs with the project cwd; its stdout/stderr are visible to the user. |
| Init failure does not record acceptance | Non-zero exit from `codegraph init -i` prints the failure message and leaves `.claude/init-state.json` unchanged for that key. |
| Re-prompt after decline is state-aware | Skip note distinguishes "previously declined install" from "previously declined init". |
| Recorded state is overridden by environment change | `install_declined` is ignored if `installed=true`; `init_declined` is ignored if `initialized=true`. |
| README URL on accept install | Literal `https://github.com/colbymchenry/codegraph#installation` printed. |
| JS-without-package.json bootstraps | In an empty dir, selecting JS/TS triggers `js-project-init`, then Stryker installs successfully (no opaque npm error). Measured: zero npm errors in init transcript. |
| JS-with-package.json unchanged | In a dir with existing `package.json`, init behavior is byte-for-byte identical to current behavior modulo the new CodeGraph prompt step. |
| Hook warns on multi-file exploration | In a project with `.codegraph/`, agent grep across `src/**/*.ts` (>2 files) produces the nudge message to stderr on the first such call of a turn. |
| Hook silent on single-file read | Reading exactly one named file produces no nudge output. |
| Hook silent after codegraph_* used | After `codegraph_context` is called, subsequent Grep/Read in same turn is silent. |
| Hook silent without .codegraph/ | Projects without `.codegraph/` see zero hook output. |
| Careful mode blocks | With `/careful` active, the multi-file exploration scenario exits 2 and the tool call does not execute. |
| Hook fails open | Inducing a hook script error (e.g. corrupting jq input) does NOT block the tool call. |
| Hook overhead < 50ms | Median wall-clock added by the hook on a quiet call is under 50ms (measured: 20 invocations, median). |
| No regression in destructive-guard | Existing destructive-guard tests still pass. |
| Both plugins ship the prompt | The `writing-core` PR mirrors the prompt step; the hook is dev-team-only. |

## Consistency Gate

- [x] Intent is unambiguous — two developers reading this would build the same state classifier + prompt + hook semantics.
- [x] Every behavior in the intent has a corresponding BDD scenario (all four (installed × initialized) cells, init execution success/failure, re-run skip notes, environment-change overrides, JS bootstrap branch, hook warn/silent/block/fail-open paths).
- [x] Architecture constrains without over-engineering — state classifier is one helper, init execution is the user's own `codegraph` binary, no install attempt, reuses existing careful-state and jq.
- [x] Terminology consistent — "CodeGraph" (product), "`.codegraph/`" (directory marker), "codegraph_*" (MCP tool family), `install_accepted`/`install_declined`/`init_accepted`/`init_declined` (state keys) used the same way across all four artifacts.
- [x] No contradictions — warn-by-default + block-in-careful matches the destructive-guard precedent; "offer to run init" matches the install-prompt's user-confirm posture.

**Verdict: PASS.** Ready for `/plan` v2.
