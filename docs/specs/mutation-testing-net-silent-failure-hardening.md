<!-- spec-version: 1 -->
# Spec: Mutation-Testing Silent-Failure Hardening (issues #554, #557, #558, #559)

## Intent Description

Today the mutation-testing skill's Stryker.NET workflow silently produces meaningless output under three common failure modes: (a) Stryker's mutation-switch runtime never observes mutations at runtime — xunit.v3 + MTP is the reproducer, but the failure surfaces on xunit.v2 too when `SolutionPath` re-enumerates test projects (#554, #557); (b) a `.sln`-hiding step is required for correct project discovery but every operator reinvents its `trap`-based restore logic and leaks the hidden state on Ctrl-C (#559); (c) long runs (15 min – multiple hours) emit no operator-facing status, so silent hangs and silent config errors burn the whole run before the summary reveals the problem (#558).

The change hardens the skill against all three modes with one coherent unit of shipped work: a mandatory workflow-enforced smoke gate, a shipped wrapper script that owns `DOTNET_ROOT`, `.sln`-hiding + trap-restore, safe log redirection, and a bash background status loop grepping the log for known-broken signatures. The reference (`csharp-stryker-net.md`) grows a `SolutionPath` warning; SKILL.md grows a language-agnostic long-run inspection section that other language files inherit later.

The success condition is that a first-time operator following the reference on macOS + .NET 10 + xunit.v3 gets either a valid mutation score or an early, specific, actionable error — never a silent 0.00% or a wedged-log run.

## Architecture Specification

### Components affected

- `plugins/dev-team/skills/mutation-testing/SKILL.md` — add Step 1c (workflow-enforced smoke gate), add long-run inspection section (language-agnostic).
- `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` — add `SolutionPath` trap warning; link to the shipped wrapper; note the smoke gate is authoritative in SKILL.md, not duplicated here.
- `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net-wrapper.sh` — **new file, shipped as a reference template** (not executed by the skill). Operators `cp` it into their repo's `scripts/`.
- `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net-status-loop.sh` — **new file**, sourced by the wrapper; owns the 10-min status/error-inspection loop so it stays testable in isolation.

### Interfaces

- **Smoke gate contract (Step 1c).** The skill runs Stryker against a single covered file first, then parses the summary. If `Killed == 0 && Survived > 0`, the workflow halts before the full run with a specific error message referencing #554/#557 and the diagnostic checklist. The gate is deterministic — it reads the tool's report JSON, not stdout heuristics — so it works with any reporter configuration.
- **Wrapper CLI.** `csharp-stryker-net-wrapper.sh [stryker-args...]` — forwards `"$@"` to `dotnet stryker` unchanged. Header vars (`SLN`, `SHIM_PROJECT`, `STRYKER_BIN`) at the top of the file, edited per-repo. No sub-flags of its own; anything else on the command line is Stryker's.
- **`.sln` hiding — always on.** The wrapper unconditionally moves `${SLN}` → `${SLN}.stryker-hidden` before invoking Stryker and restores via `trap restore_sln EXIT INT TERM`. Chosen over opt-in because #557 shows the failure mode is silent (Stryker prefers a re-enumerated test project) — an opt-out flag would let the trap regress unnoticed.
- **Status loop.** The wrapper forks a bash background loop (`--status-interval` — default 600 s, configurable, `0` disables). Each tick emits one line: `<slice>: N/M tested, K killed, S survived, T timeout, elapsed HH:MM`. If the log grep matches any red-flag signature (`Killed: 0` with `Survived: > 0`, `CompileError` count > threshold, `SolutionPath` line naming an unexpected `.sln`, dead process while log is still open), emit a distinct `[RED-FLAG]` line naming the failure mode and its documented workaround. The loop is a portable bash background job, not a Claude Code Monitor — the wrapper works outside Claude Code (CI, direct terminal).
- **Log redirection.** Wrapper uses `> "$LOGFILE" 2>&1` (or `set -o pipefail` when `--tee`), never bare `| tee` — enforces #550 at the file level so no downstream operator can regress it.

### Dependencies

- Requires bash 3.2+ (macOS-safe idioms), `dotnet` on PATH, and the environment preamble the current reference already documents. No new tool dependencies.
- Uses `pgrep`, `grep -E`, `date +%s`, `awk` — all present on macOS and Linux; the wrapper does not target Windows Git Bash (mutation testing on Windows uses different .NET tooling; addressed separately if it becomes a supported target).

### Constraints

- **Smoke gate cannot be skipped without explicit override.** No `--skip-smoke` flag by default; if the workflow-managed-approval carve-out ever needs it, add via an explicit register-caller step, not a bare flag.
- **Wrapper is shipped as a template, not invoked by the skill.** Operators own the copy in their repo — this matches the existing plugin convention (skill references show idioms, don't execute them) and keeps the wrapper editable per-repo without a plugin version bump.
- **Long-run inspection lives in SKILL.md, not the C# reference.** Same failure modes apply to Stryker/pitest/mutmut/go-mutesting; the C# reference points at SKILL.md's section and only adds Stryker.NET-specific signatures.
- Existing configuration keys (`coverage-analysis`, `additional-timeout`, `testTimeout`, `PreserveNewest`) stay authoritative — this change does not renegotiate #522 / #528's decisions.

## Acceptance Criteria

### Smoke gate (from #554, #557)

- [ ] SKILL.md contains a Step 1c that runs a single-file Stryker probe and parses the resulting `mutation-report.json` for kill counts before authorizing the full run.
- [ ] When Step 1c returns `Killed == 0 && Survived > 0`, the skill halts with an error that (a) names the failure mode ("mutation-switch not observing mutations at runtime"), (b) links to issues #554 and #557, and (c) enumerates the diagnostic checklist (verify manual mutation kills the test; check `SolutionPath` config; confirm not preferring an unintended test project).
- [ ] When Step 1c returns any `Killed > 0`, the full run proceeds.
- [ ] `csharp-stryker-net.md` xunit.v3 section links to Step 1c rather than duplicating the smoke procedure.

### `SolutionPath` warning (from #557)

- [ ] `csharp-stryker-net.md` has a `SolutionPath` warning: a config with both `SolutionPath` and `TestProjects` set may enumerate additional test projects from the solution and prefer them over the ones listed in `TestProjects`.
- [ ] The warning enumerates the three remediation paths (remove `SolutionPath`, exclude the main test project via config, downgrade the main test project to xunit.v2) and names which the plugin recommends.

### Wrapper script (from #559)

- [ ] `references/languages/csharp-stryker-net-wrapper.sh` exists, executable, `set -euo pipefail`.
- [ ] Wrapper always hides `${SLN}` before invoking Stryker and restores via `trap restore_sln EXIT INT TERM` (`INT` and `TERM` both covered).
- [ ] Trap restore is idempotent — running the wrapper when a stale `${SLN}.stryker-hidden` already exists does not clobber a fresh `.sln`.
- [ ] Wrapper exports `DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"` (idempotent — respects a pre-set value).
- [ ] Wrapper pre-builds `${SLN}` and `${SHIM_PROJECT}` (when set) before hiding the `.sln`.
- [ ] Wrapper forwards `"$@"` to `dotnet stryker` unchanged.
- [ ] Wrapper redirects with `> "$LOGFILE" 2>&1` (or `set -o pipefail`), never a bare pipe to `tee`.
- [ ] Header vars (`SLN`, `SHIM_PROJECT`, `STRYKER_BIN`, `LOGFILE`, `STATUS_INTERVAL`) sit in a clearly-marked block at the top of the file for per-repo edits.

### Status loop (from #558)

- [ ] `references/languages/csharp-stryker-net-status-loop.sh` exists and is sourced by the wrapper.
- [ ] Default status interval is 600 s; overridable via `STATUS_INTERVAL` env var; `STATUS_INTERVAL=0` disables the loop.
- [ ] Each tick emits one status line with mutants-tested/total, kills, survivors, timeouts, elapsed wall-clock — read from the log or report JSON, not from Stryker's ANSI `progress` reporter.
- [ ] The reference tells operators to configure `reporters: ["dots", ...]` (or equivalent non-ANSI reporter) so log parsing is deterministic.
- [ ] The loop greps each tick for red-flag signatures: `Killed: 0` co-occurring with `Survived: > 0`; `CompileError` count exceeding a documented threshold (proposed: 25); `SolutionPath` naming a `.sln` when a `test-projects` list was set; test-host or main Stryker process dead while log is still being written.
- [ ] On any red-flag hit, the loop emits a distinct `[RED-FLAG]` line naming the specific failure mode and its documented workaround (link to the relevant issue).
- [ ] Loop shuts down cleanly when the wrapper exits (trap kills the background PID).

### Long-run inspection guidance (from #558, language-agnostic)

- [ ] SKILL.md gains a "Long-run inspection" section (after Step 2, before Step 3) documenting the three signals (progress, health, error inspection) and the 10-min default cadence.
- [ ] Section notes that language references may add tool-specific red-flag signatures; C# reference is the first example.
- [ ] Section does not mandate a specific implementation — it describes the contract; the shipped C# wrapper is one implementation, an in-session Monitor is another.

### Cross-cutting

- [ ] All new shell scripts pass `shellcheck` with no findings.
- [ ] Bats tests cover: smoke-gate happy path; smoke-gate failure detection; wrapper trap on `EXIT`, `INT`, `TERM`; wrapper idempotency vs pre-existing hidden `.sln`; status loop red-flag emission for each documented signature.
- [ ] Every change lands on a feature branch via a PR titled `feat(mutation-testing): ...` per repo convention.
- [ ] Local gate (`scripts/ci-local.sh`) passes end-to-end before push.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Smoke gate — workflow-enforced or prose-only? | `requires-stakeholder-input` | human | Workflow-enforced. Silent 0% is the highest-severity mode; prose guidance is provably ignored. |
| Status loop — bash wrapper, Claude Code Monitor, or both? | `requires-stakeholder-input` | human | Bash wrapper only. Portability across CI + direct terminal outweighs one extra Monitor surface. |
| `.sln` hiding — default on or opt-in? | `requires-stakeholder-input` | human | Default on. Trap restores on any exit path; opt-in would let the trap regress unnoticed. |
| Long-run inspection — SKILL.md or C# reference? | `requires-stakeholder-input` | human | SKILL.md. Failure modes are language-agnostic; C# reference adds Stryker.NET-specific signatures on top. |
| Status interval default — 5, 10, or 15 min? | `inferable` | inference | 10 min (600 s). #558 explicitly proposes this cadence — enough resolution to catch a stall within one cycle, infrequent enough not to spam operator output. |
| CompileError threshold for red-flag | `inferable` | inference | 25. Low enough to catch a probe-file misconfig on a small file; high enough not to fire on a file that legitimately has 10–15 CompileError mutants from a generator. Configurable via env var so ops can tune. |
| Should the wrapper support Windows Git Bash? | `inferable` | inference | No — mutation testing on Windows uses different .NET tooling paths and no user has requested it. Wrapper header documents "macOS/Linux only" so a Windows attempt fails loudly, not silently. |
| Where does the wrapper live in the plugin? | `inferable` | inference | Under `references/languages/` next to the language file that documents it. The reference calls the wrapper "a shipped template — copy into your repo's `scripts/`," matching the existing convention that references show idioms, not runtime dependencies. |
| Smoke-gate skip flag? | `inferable` | inference | No default flag. If workflow-managed-approval callers need one later, they register through the existing carve-out mechanism (`references/workflow-callers.md`); no bare `--skip-smoke` is exposed. |
| Test coverage — bats sufficient? | `inferable` | inference | Yes — the plugin already tests shell scripts via bats and this repo's `hermetic` helper. No new test framework needed. |
| Which reporter to standardize on for log parsing? | `inferable` | inference | Stryker's `dots` reporter is documented in #558 as the survives-redirection choice. Reference recommends `["dots", "json", "html"]` so status loop reads dots + summary reads JSON. |

## Consistency Gate

- [x] Intent is unambiguous — hardens the .NET recipe against three named silent-failure modes with one coherent unit of work.
- [x] Every behavior/goal in the intent maps to at least one acceptance criterion (smoke gate → #554/#557 ACs; wrapper → #559 ACs; status loop → #558 ACs; SolutionPath → #557 AC).
- [x] Architecture constrains implementation to the shipped-template pattern the plugin already uses; no runtime dependencies or new frameworks introduced.
- [x] Terminology consistent — "smoke gate", "wrapper", "status loop", "red-flag signature", ".sln hiding" used identically across all three sections.
- [x] No contradictions between artifacts — SKILL.md owns the language-agnostic contract, csharp-stryker-net.md owns the .NET specifics, wrapper implements them; no section redefines another's authority.
- [x] Every gap/ambiguity finding is logged — all four stakeholder decisions captured from the AskUserQuestion round; all inferences carry explicit rationale.

**Verdict: PASS.** Ready for `/plan`.
