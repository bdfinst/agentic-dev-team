<!-- spec-version: 1 -->
# Spec: Mutation-Testing Smoke Gate Hook (issue #565)

## Intent Description

PR #562 shipped Step 1c of the mutation-testing SKILL.md as workflow prose the agent is instructed to follow before authorizing a full mutation run. The Strategic Critic during that plan-review round objected to prose-only enforcement ("provably ignored") and I acknowledged then shipped it anyway. This spec is the correction: promote the Step 1c smoke gate from prose-that-can-be-ignored into a Claude Code `PreToolUse` hook that mechanically blocks whole-scope Stryker.NET invocations until a smoke run has been executed and its `mutation-report.json` reports `Killed > 0`.

The failure mode this prevents is specific and named — the mutation-switch not observing mutations at runtime, causing hours of Stryker execution to produce a meaningless `0.00%` score (issues #554 and #557). Prose enforcement asks the agent to remember Step 1c before every whole-scope run; a hook does not ask, it checks. The hook and the prose describe the same rule; the hook is the mechanism, the prose is the explanation. Neither replaces the other — the prose stays because it explains *why* the gate exists, and operators reading SKILL.md still need that context.

Success looks like: an operator (or an agent) issues `dotnet stryker --config-file stryker-config.json --mutate '**/Validators/**/*.cs'` in Claude Code, the hook fires, sees no recent smoke report, blocks the run with the diagnostic checklist naming #554/#557, and instructs how to run the smoke probe first. When the operator runs `dotnet stryker --config-file stryker-config.json --mutate 'src/Validators/WalletValidator.cs' -O StrykerOutput/smoke` and the resulting `mutation-report.json` shows `killed > 0`, the next whole-scope invocation passes the gate silently. When it shows `killed == 0 && survived > 0`, the gate blocks the whole-scope run and surfaces the mutation-switch failure diagnosis — before the operator burns hours on a full run.

## Architecture Specification

### Components affected

- `plugins/dev-team/hooks/mutation-testing-smoke-gate.sh` — **new file**. PreToolUse hook implementing the smoke gate.
- `plugins/dev-team/settings.json` — register the hook under the existing `PreToolUse.Bash` matcher block.
- `plugins/dev-team/skills/mutation-testing/SKILL.md` — Step 1c gains a note that a hook now enforces the check; documents the fixed report path and the escape hatch.
- `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` — brief cross-reference to the hook alongside the existing Step 1c link.
- `tests/hooks/mutation_testing_smoke_gate.bats` — **new file**. Contract tests using hermetic fixtures and the existing hook-test idioms (stdin JSON, exit-code protocol, stdout messages).
- `tests/hooks/fixtures/stryker-net/` — reuse existing fixture reports where possible; add fresh ones only when a variant is missing.

### Interfaces

**Hook contract (PreToolUse protocol):**

- Input: JSON on stdin, extracts `.tool_input.command` (the bash command string).
- Output:
  - **Silent pass** (exit 0, no stdout) when the command doesn't match a whole-scope Stryker invocation, or when the smoke report is present and passes.
  - **Block** (exit 2, message on stdout) when the command matches AND no smoke report exists, OR smoke report shows `killed == 0 && survived > 0`, OR smoke report shows `killed == 0 && survived == 0` (no-signal probe).
  - **Skip silently** (exit 0, no stdout) when `MUTATION_SMOKE_GATE_SKIP=1` — bypass appended to `metrics/gate-bypass.jsonl` (one line per bypass) for audit.
- Hook name in output messages: `mutation-testing-smoke-gate`.

**Trigger patterns** (command must match ALL of):

1. Command contains `dotnet stryker` OR ends in a path to `csharp-stryker-net-wrapper.sh`.
2. Command does NOT contain a `--mutate` argument whose value is a single-file path (no glob metacharacters — no `*`, no `**`, no `?`, no `[...]`).

Rationale: single-file `--mutate` scoping IS the smoke probe itself. The gate must not block the very command that produces the report it will later check. Any broader scope (multi-file glob, missing `--mutate` entirely, wildcard-only glob) is a "whole-scope" run subject to the gate.

**Trigger detection is opinionated, not perfect.** A command like `dotnet stryker --mutate 'src/Foo.cs;src/Bar.cs'` (Stryker's `;`-separated multi-file syntax) counts as multi-file and triggers the gate. Operators who need to bypass on a legitimate single-run exception use `MUTATION_SMOKE_GATE_SKIP=1` for that invocation.

**Smoke report path — fixed convention:**

- Location: `<cwd>/StrykerOutput/smoke/reports/mutation-report.json`.
- Parsed via `jq` for `.killed`, `.survived` counts (the schema Stryker.NET writes matches the JS Stryker JSON report — same shape).
- Report freshness NOT checked in v1. If an operator runs a smoke probe and then modifies test code, the stale report will pass the gate. This is a known limitation; documented in the escape-hatch prose.
- SKILL.md's Step 1c gets an explicit "run the smoke probe with `-O StrykerOutput/smoke`" instruction so the report lands at the path the hook checks.

**Block message shape:**

```
[BLOCK] mutation-testing-smoke-gate: whole-scope Stryker.NET run detected without a passing smoke report

The Step 1c smoke gate (see SKILL.md § Step 1c) requires you to run a single-file
mutation probe first and verify Killed > 0 before authorizing a full run. This
prevents the silent 0.00% failure mode caused by the mutation-switch not observing
mutations at runtime (see #554, #557).

<one of three specific diagnostics>

To run the smoke probe:

  dotnet stryker --config-file stryker-config.json \
    --mutate 'path/to/one/covered/file.cs' \
    -O StrykerOutput/smoke

Then re-run this command. To bypass this gate for a legitimate exception, set
MUTATION_SMOKE_GATE_SKIP=1 in the environment (audit-logged).
```

The `<one of three specific diagnostics>` is one of:

- `No smoke report found at StrykerOutput/smoke/reports/mutation-report.json.`
- `Smoke report reports Killed=0, Survived=<n> — mutation-switch is not observing mutations. See the diagnostic checklist in SKILL.md Step 1c.`
- `Smoke report reports Killed=0, Survived=0 — no scored mutants; pick a different probe file with real test coverage.`

**Escape hatch:**

- Env var: `MUTATION_SMOKE_GATE_SKIP=1`.
- Behavior: hook exits 0 silently.
- Audit: appends one JSON line to `<cwd>/metrics/gate-bypass.jsonl` with `{"timestamp": "<ISO8601>", "hook": "mutation-testing-smoke-gate", "command_hash": "<sha256 first 16 chars>", "cwd": "<cwd>"}`. Command itself is NOT logged (privacy — matches the cost-meter's privacy boundary), only a hash to correlate multiple bypasses of the same command.
- The `metrics/` directory is created if it doesn't exist. If it can't be created (permission denied), the bypass still succeeds — audit failure is logged to stderr but doesn't block the operator.

### Dependencies

- `jq` — hard dependency. Fail-safe pattern matches `mutation-gate.sh`: if `jq` isn't installed, emit an ADVISORY message and exit 0 (do NOT block; a missing tool must not be a de facto gate).
- `python3` — used for the `date +%N` fallback and JSON manipulation portions matching existing hook idioms. Same fail-safe treatment.
- No new hard dependencies beyond what the mutation-testing skill already requires.

### Constraints

- **PreToolUse-only.** The hook runs inside Claude Code, not on CI or in direct-terminal runs. This matches the existing hook infrastructure — hooks are Claude-Code specific. Documented explicitly in the hook file's header.
- **Cross-platform (macOS, Linux, Windows Git Bash).** Per `feedback_all_scripts_platform_neutral`, no GNU-only flags, no hard-coded macOS paths. Uses `jq`, `python3`, `[`, `grep`, `sed` — all cross-platform.
- **Bash 3.2-safe.** Per CLAUDE.md; empty-safe array expansion where applicable.
- **shellcheck clean.**
- **The hook is additive.** It does NOT replace Step 1c prose in SKILL.md; the prose still describes the rule and the diagnostic checklist. The hook is the enforcement mechanism.
- **Detection is line-based, not shell-parsed.** The hook uses regex against the command string; it does NOT execute or dry-run the command. A command with obscure shell escaping (heredocs, arrays, eval) may bypass detection — documented as a known limitation, matching how the existing `destructive-guard.sh` handles the same class of edge case.

## Acceptance Criteria

- [ ] `plugins/dev-team/hooks/mutation-testing-smoke-gate.sh` exists, executable, `set -uo pipefail`, header names its purpose + refs #565.
- [ ] Hook registered in `plugins/dev-team/settings.json` under the existing `PreToolUse.Bash` matcher block (alongside `destructive-guard.sh`, `pre-commit-review.sh`, etc.).
- [ ] Hook silent-passes when the command doesn't contain `dotnet stryker` and doesn't reference the wrapper script.
- [ ] Hook silent-passes when the command has a `--mutate` argument whose value is a single-file path (no glob metacharacters).
- [ ] Hook silent-passes when the command triggers the gate AND `StrykerOutput/smoke/reports/mutation-report.json` exists AND reports `killed > 0`.
- [ ] Hook **blocks** (exit 2) when the command triggers the gate AND no smoke report exists — block message names the missing path.
- [ ] Hook **blocks** (exit 2) when the command triggers the gate AND report shows `killed == 0 && survived > 0` — block message names the observed counts, references #554 and #557, and points at the diagnostic checklist in SKILL.md Step 1c.
- [ ] Hook **blocks** (exit 2) when the command triggers the gate AND report shows `killed == 0 && survived == 0` — block message says "no scored mutants; pick a different probe file."
- [ ] Every block message includes the `dotnet stryker --config-file ... --mutate '...' -O StrykerOutput/smoke` example command.
- [ ] Every block message names `MUTATION_SMOKE_GATE_SKIP=1` as the escape hatch.
- [ ] When `MUTATION_SMOKE_GATE_SKIP=1` is set: hook exits 0 silently AND appends one line to `<cwd>/metrics/gate-bypass.jsonl` with `timestamp`, `hook`, `command_hash` (sha256, first 16 chars), `cwd`.
- [ ] `metrics/` is created if absent; permission failure on write logs to stderr but does not block.
- [ ] Missing `jq` → advisory message (not a block), exit 0. Same pattern as `mutation-gate.sh`.
- [ ] Missing `python3` → advisory, exit 0.
- [ ] SKILL.md Step 1c gains a paragraph that: (a) names `mutation-testing-smoke-gate.sh` as the enforcing mechanism, (b) instructs running the smoke probe with `-O StrykerOutput/smoke`, (c) documents the escape hatch env var and audit-log path.
- [ ] `csharp-stryker-net.md` gains one sentence cross-referencing the hook alongside the existing Step 1c link.
- [ ] `shellcheck` clean on the new hook.
- [ ] Bats tests cover: silent-pass on non-Stryker commands; silent-pass on wrapper invocations without stryker; silent-pass on single-file `--mutate`; block on missing report; block on `killed==0 && survived>0`; block on `killed==0 && survived==0`; silent-pass on `killed>0`; escape hatch honored + audit line written; missing `jq` → advisory; malformed JSON report → advisory (not silent-pass — a malformed report is not a valid pass).
- [ ] Hook script cross-platform per `feedback_all_scripts_platform_neutral` — no GNU-only flags, no hard-coded macOS paths.
- [ ] Local gate (`scripts/ci-local.sh`) passes.
- [ ] PR title conventional: `feat(mutation-testing): pretooluse hook enforces step 1c smoke gate (#565)`.
- [ ] PR body uses `Closes #565`.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Smoke report path — fixed / env var / search? | `requires-stakeholder-input` | human | Fixed: `StrykerOutput/smoke/reports/mutation-report.json`. Simple, one path to document and check. SKILL.md's Step 1c will instruct running the smoke probe with `-O StrykerOutput/smoke`. |
| Gate trigger — how broad? | `requires-stakeholder-input` | human | Broadest: any `dotnet stryker` (or shipped wrapper) without a single-file `--mutate` glob triggers. Multi-file globs count as whole-scope. Matches the failure mode's severity — the silent-0% risk exists on any whole-scope run, not just missing-`--mutate` ones. |
| Escape hatch behavior — silent + audit / stderr warning / silent no log? | `requires-stakeholder-input` | human | Silent + audit-log to `metrics/gate-bypass.jsonl`. Consistent with `MUTATION_GATE_SKIP=1` on `mutation-gate.sh` and the cost-meter's privacy boundary. |
| Scope — PreToolUse-only / dual with wrapper? | `requires-stakeholder-input` | human | PreToolUse-only. Hook covers Claude Code; direct-terminal + CI operators rely on the shipped wrapper's own defenses (prose + Step 1c). Two enforcement surfaces cost more to maintain than they save today. |
| Report freshness check — timestamps or ignore? | `inferable` | inference | Ignore in v1. Adding a freshness check needs a heuristic ("newer than test files"?) that's easy to get wrong. Stale-report false-passes are documented as a known limitation; if operator confusion surfaces, add later. |
| Command-hash algorithm — sha256 / md5 / no hash? | `inferable` | inference | sha256, first 16 chars. Matches `cost-meter.sh`'s privacy hashing pattern. First 16 chars balances collision resistance vs. audit-log readability. |
| Where does gate-bypass.jsonl live — repo-scoped `<cwd>/metrics/` or global `~/.claude/metrics/`? | `inferable` | inference | `<cwd>/metrics/`. Consistent with the plugin's existing metrics collection under `metrics/` (per CLAUDE.md orchestration doc). Repo-scoped means per-project bypass patterns are traceable. |
| Command detection — regex or shell parse? | `inferable` | inference | Regex against the command string. Same approach `destructive-guard.sh` uses. Shell parsing is out of scope; obscure escaping is documented as a known limitation. |
| Behavior on jq/python3 missing — block, advisory, or silent pass? | `inferable` | inference | Advisory + exit 0. A missing dependency must not become a de facto gate — that's the same pattern as `mutation-gate.sh`. |
| Malformed report JSON — block, advisory, or pass? | `inferable` | inference | Advisory + exit 0. A malformed report means the tool ran but produced garbage — the gate can't reason about it; surface the anomaly, let the operator decide. |
| Should the hook's stdout include the raw block message OR a JSON envelope? | `inferable` | inference | Raw block message on stdout. `destructive-guard.sh` uses raw stdout; matching that pattern. The `hookSpecificOutput` JSON envelope is `mutation-gate.sh`'s pattern (PostToolUse) and different from PreToolUse's raw-block convention. |
| PR title convention (feat vs. fix)? | `inferable` | inference | `feat` — adds a new capability (a hook), doesn't correct a defect. The prose was intentional at the time it shipped; this ADDS mechanical enforcement. |

## Consistency Gate

- [x] Intent is unambiguous — promote Step 1c smoke gate from prose to a PreToolUse hook that blocks whole-scope Stryker.NET invocations until a passing smoke report exists.
- [x] Every behavior/goal maps to an acceptance criterion (trigger detection → 3 ACs; report presence + parse → 4 ACs; escape hatch + audit → 2 ACs; missing deps → 2 ACs; SKILL.md/CSHARP.md updates → 2 ACs; test coverage → 1 aggregated AC; cross-platform + shellcheck + PR → 4 ACs).
- [x] Architecture constrains implementation — fixed report path, regex-based detection, jq/python3 fail-safes match existing hook patterns.
- [x] Terminology consistent — "smoke gate", "whole-scope", "single-file probe", "escape hatch", "audit log" used identically across all three sections.
- [x] No contradictions between artifacts — Intent's mechanical-enforcement goal, Architecture's exit-2-block contract, and Acceptance's block-message content all agree.
- [x] Every gap/ambiguity finding is logged — 4 `requires-stakeholder-input` items resolved by human; 8 `inferable` items with explicit rationale.

**Verdict: PASS.** Ready for `/plan`.
