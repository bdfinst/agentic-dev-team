---
name: test-modernize
description: >-
  Modernize a legacy repository's tests for CD as one orchestrated workflow —
  assessment, public-interface Gherkin, disable cannot-fail tests with baseline
  coverage, add every test that needs no production-code refactoring, then
  minimum refactor-for-testability until coverage, mutation, determinism, and
  speed targets are met. Outputs phase issues to ADO, GitHub, GitLab, Jira, or
  local plans/specs files — whichever the parent issue URL resolves to (empty
  falls back to local files).
argument-hint: "<repo-path> [--parent <issue-url>] [--ci <path>] [--external-tests <loc>] [--stack <id>] [--from-phase <n>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill(cd-test-architecture *), Skill(issues-from-assessment *), Skill(gherkin-public *), Skill(test-audit-disable *), Skill(coverage-baseline *), Skill(coverage-delta *), Skill(quality-targets-converge *), Skill(build *), Skill(mutation-testing *)
---

# Test Modernize

Role: orchestrator. This command sequences existing skills/agents through the five-phase legacy-test-modernization workflow; it does not implement, audit, or write tests itself. Each phase is delegated to the worker skill that owns it, the workflow gates on human approval between phases, and per-phase progress is persisted to `memory/test-modernize/<repo>/phase-<n>.md` so `/continue` (and `--from-phase`) can resume.

You have been invoked with the `/test-modernize` command.

## Orchestrator constraints

1. **Delegate every phase.** Call the owning skill or agent (`/cd-test-architecture`, `/issues-from-assessment`, `/gherkin-public`, `/test-audit-disable`, `/coverage-baseline`, `/build`, `/coverage-delta`, `/mutation-testing`, `/quality-targets-converge`); run `python3 scripts/test_modernization_review.py --repo <slug> --phase <n>` for phase-boundary reviews; do not re-implement their logic here.
2. **Honor the human gates.** Do not advance past a gate without explicit approval — this command sequences phases, it does not remove their review points.
3. **Confirm the approach first.** Surface every ambiguous input (repo path, parent issue URL, CI config, external test sources, quality targets) in a single batch before Phase 1 starts.
4. **Be concise.** Report each phase's outcome and the next gate, nothing more.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>` (required) — the legacy repo under modernization.
- `--parent <issue-url>` — parent issue URL on ADO / GitHub / GitLab / Jira. Empty or omitted → local-files mode.
- `--ci <path>` — existing pipeline config (azure-pipelines.yml / .github/workflows / Jenkinsfile). Passed through to `/cd-test-architecture`.
- `--external-tests <loc>` — other-repo suites, Postman collections, manual scripts. Passed through to `/cd-test-architecture`.
- `--stack <id>` — override stack detection (default: detect from manifests in Step 0). Resolved profile key like `dotnet`, `node`, `spring-boot`, `go`, `django`, `react`, `vue`, `ssr-htmx`. Passed through to `/cd-test-architecture` so the orchestrated flow does not double-scan.
- `--from-phase <n>` — resume from phase `n` (skips earlier phases when their progress files exist).

## Steps

### 0. Approach contract

Resolve the sink and the inputs in a single batch:

1. Confirm `<repo-path>`. If absent or invalid, ask the operator.
2. **Parent issue URL.** If `--parent` was given, parse the host; otherwise ask: "Parent issue URL? (ADO / GitHub / GitLab / Jira — or leave empty for local files.)"
3. Map host → CLI:
   - `dev.azure.com` → `az` (extension: `az boards`).
   - `github.com` → `gh`.
   - `*.atlassian.net` → `acli` (Atlassian CLI; REST + `JIRA_TOKEN` is the fallback).
   - `gitlab.com` (or self-hosted GitLab) → `glab`.
   - empty → **local-files mode** (writes to `./plans/test-modernize/` and `./specs/test-modernize/`).
4. Probe the chosen CLI with `command -v <cli> >/dev/null 2>&1`. If missing, inform the operator with the exact install command and **fall back to local-files mode** for the rest of the workflow.
5. Confirm CI config path and external test sources (if any). Defaults: none.
6. Quality targets — defaults `coverage ≥ 90%`, `surviving mutants = 0`, `determinism = 100%`, `pre-merge wall-clock = fastest achievable`. Mention that `.dev-team/quality-targets.json` can override them per-repo; load it if present.
7. **Test-binding mode for the approved Gherkin** — ask the operator which to use, defaulting to `xunit-with-annotations`:
   - `bdd-runner` — generate step definitions in the project's BDD runner (cucumber-js, pytest-bdd, behave, cucumber-jvm, SpecFlow, godog) so each Scenario executes its Given/When/Then steps directly.
   - `xunit-with-annotations` (default) — one xUnit-style test method per Scenario; the test method name mirrors the Scenario name, and the Given/When/Then become structured comments at the top of the test body citing the source `.feature` file.
   Record the choice in `memory/test-modernize/<slug>/phase-0.md`; `/gherkin-public` reads it to populate the `[Component tests]` Story bodies.
8. **Detect stack.** Resolve the project's stack from manifests so Phase 1 can forward `--stack <id>` to `/cd-test-architecture` (no double-scan in the orchestrated flow). The resolved identifier is the key for `knowledge/test-stack-profiles/<stack>.md`, which `/cd-test-architecture` will load. Mirrors `skills/test-design-advisor/SKILL.md:31, 62`: when `--stack <id>` was passed to `/test-modernize`, it takes precedence and detection is skipped. Otherwise, read manifests at `<repo-path>` — `package.json` (refined to react/vue via dependency, or to ssr-htmx when an htmx dep is present alongside `templates/*.html`), `*.csproj` / `*.sln`, `pom.xml` / `build.gradle*`, `go.mod`, `pyproject.toml` / `requirements.txt` — and resolve the matching profile key. When no profile matches, fall through to stack-agnostic guidance and **name the missing profile** in `memory/test-modernize/<slug>/phase-0.md` — never block on it. Record the resolved stack (or the missing-profile note) in `phase-0.md` so `/continue` and `--from-phase` resumes preserve it.
9. Generate a `<repo-slug>` (last path segment, lowercased, non-alphanumerics → `-`). All progress files live under `memory/test-modernize/<repo-slug>/`.

Print the resolved inputs (sink, CLI, fallback decision, targets, `<repo-slug>`) and proceed. If `--from-phase <n>` was given, jump to that phase.

### 1. Analyze — `/cd-test-architecture` + `/issues-from-assessment`

1. Invoke `/cd-test-architecture <repo-path> [--ci <ci-path>] [--external-tests <loc>] [--stack <stack>]`. The `--stack` value is the one resolved in Step 0 (or the explicit override) — passing it forwards the stack identifier so `/cd-test-architecture` does not re-scan manifests. It writes the assessment to `reports/cd-test-architecture-<app>.md`.
2. Invoke `/issues-from-assessment <assessment-path> --parent <url-or-empty> --repo-slug <slug>`. It creates the parent + Phase-1 / Phase-2 / Phase-5 children via the resolved CLI (or local plan files) and writes a per-phase index to `memory/test-modernize/<slug>/phase-1.md`.
3. Run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 1`. Surface any blocker findings to the operator and have them resolved before the gate.

**Human gate** — wait for approval before specifying the public interface.

### 2. Specify public interface — `/gherkin-public` (two-pass)

Phase 2 runs in two passes around the human gate so Stories never bind to un-reviewed scenarios.

**Pass A — author scenarios.**

1. Invoke `/gherkin-public <repo-path> --repo-slug <slug>`. It reads the component map from `memory/test-modernize/<slug>/phase-1.md` and writes `.feature` files per public surface (API endpoint, UI flow, batch-job entry point, library export, event type) to `features/test-modernize/` (or `./specs/test-modernize/` if no `features/` dir exists). It does NOT create Stories on this pass.
2. Run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 2`.

**Human gate** — operator validates the Gherkin scenarios. This is a hard stop. The operator may edit `.feature` files in place before approving.

**Pass B — bind Stories to approved scenarios.**

1. Once approved, invoke `/gherkin-public <repo-path> --repo-slug <slug> --parent <url-or-empty> --create-stories`. This pass creates one `[Component tests] <component> · <surface>` Story per approved public surface via the resolved tracker CLI. Each Story's Acceptance Criteria cites the specific `<feature-file>::<scenario-name>` pairs its tests must satisfy. The scenario → Story-id map is written to `memory/test-modernize/<slug>/gherkin-bindings.json`.
2. Backfill the predecessor placeholders the Phase-1 Stories left for `[Component tests]` (contract / integration / E2E / resilience Stories blocked by the new Story IDs).

### 3. Audit + baseline coverage — `/test-audit-disable` + `/coverage-baseline`

1. Invoke `/test-audit-disable <repo-path> --repo-slug <slug>`. Disables every cannot-fail test (skip + tag, never delete) and records reasons in `memory/test-modernize/<slug>/disabled-tests.json`.
2. Invoke `/coverage-baseline <repo-path> --parent <url-or-empty> --repo-slug <slug> --workflow test-modernize`. Runs the project's coverage tool, records the baseline at `memory/test-modernize/<slug>/baseline-coverage.json`, and posts the number to the parent issue (or `./plans/test-modernize/FEATURE.md` in local-files mode). Passing `--workflow test-modernize` keeps the memory namespace under `memory/test-modernize/` exactly as before.
3. Run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 3`.

**Human gate** — baseline accepted before adding tests.

### 3a. Review-the-phase loop (Phase 4 + Phase 5 use this identically)

This is the shared end-of-phase review the orchestrator runs at the close of Phase 4 and Phase 5. Both phases cross-reference this block rather than duplicating it. The loop converges quickly when the phase's tests are clean and escalates to the operator when they aren't — same review-fix-loop pattern `/build` uses inline, but scoped to the phase's diff.

1. Resolve the phase's base sha: the merge-base of the phase's first Story branch and `main` (`git merge-base <phase-base-ref> main`). Record it as `<phase-base-sha>` for the rest of this loop.
2. Dispatch `/test-design --since <phase-base-sha>` — produces the phase's Farley Score, test-review findings, and test-smell findings. Advisory: its output is recorded, never auto-fixed (test design is an operator-judgment call).
3. Dispatch `/code-review --since <phase-base-sha>` — runs the full review-agent suite over the phase's diff and writes correction prompts to `corrections/` for any error/warning findings.
4. **Fix loop, max 2 iterations.** If `/code-review` returned any error- or warning-severity findings with high or medium confidence:
   a. Dispatch `/apply-fixes corrections/` to land the auto-fixable corrections.
   b. Re-run `/code-review --since <phase-base-sha>`.
   c. If clean, exit the loop and continue to step 5.
   d. If still failing AND iteration count < 2, repeat (a).
   e. **After iteration 2** (still failing), halt the loop and surface the escalation prompt:

      ```text
      ⚠ Phase-<n> review fix loop did not converge after 2 iterations
        Remaining error/warning findings: <count>
        See: corrections/<latest>/

      Actions:
        [r] revise manually — apply fixes by hand, then /continue
        [w] waive          — record reason; remaining findings carry forward
        [q] quit           — halt the workflow

      Choose [r/w/q]:
      ```

      On `[w]`, append a Phase-`<n>` review waiver to `memory/test-modernize/<slug>/waivers.json` tagged with the finding list (same waivers file Phase-4 mutation halts use). On `[r]`, exit the gate and wait; `/continue` re-enters at this step. On `[q]`, halt the workflow.
5. **Tool-unavailable triage.** If `/test-design` or `/code-review` cannot run (dependency missing, plugin unavailable), surface:

   ```text
   Review tool unavailable for Phase <n>. Install via /init-dev-team,
   or skip end-of-phase review for this run.

     [i] install — invoke /init-dev-team and retry the review
     [k] skip   — proceed advisory; human gate fires without review evidence
     [q] quit   — halt the workflow

   Choose [i/k/q]:
   ```

6. Persist the review evidence to `memory/test-modernize/<slug>/phase-<n>-review.json`:

   ```json
   {
     "captured_at": "<ISO-8601>",
     "base_sha":   "<phase-base-sha>",
     "head_sha":   "<HEAD-at-loop-exit>",
     "farley_score":  { "rating": "...", "score": ... },
     "smells":        [ { "rule": ..., "file": ..., "line": ... } ],
     "code_review":   { "errors": <n>, "warnings": <n>, "suggestions": <n> },
     "iterations":    <n>,
     "escalated":     <true|false>
   }
   ```

The phase's human gate reads this file before firing — without it (escape hatch `[k]` chosen, tool unavailable), the gate surfaces "review evidence: advisory only" so the operator knows what was skipped.

### 4. Fix disabled tests + add no-refactor tests — `/build` + `/coverage-delta` + mutation gate

**Pre-flight — resolve Phase-3 disabled tests.** Before any Phase-4 child issue runs, read `memory/test-modernize/<slug>/disabled-tests.json` and walk it entry-by-entry. For each disabled test, the orchestrator must choose one outcome and record it in `memory/test-modernize/<slug>/disabled-tests-resolution.json`:

- **`repair`** — the test can be made meaningful **without changing production code** (e.g. add a real assertion, replace `expect(true).toBeTruthy()` with the actual observable behavior, remove the swallowed-exception catch). Dispatch `/build` against a `[Repair disabled test] <file>::<test>` work item that unskips the test, lands the assertion, and proves it can fail (kill the production line under test or mutate it and confirm the test goes red). The `cannot-fail:` skip tag is removed.
- **`defer-to-phase-5`** — repairing the test requires a production-code refactor (no seam to assert against, hidden collaborator, untestable side effect). Do NOT touch the test in Phase 4. Draft a Phase-5 `[Repair disabled test] <file>::<test>` defect Story into `memory/test-modernize/<slug>/phase-5.md` that cites `file:line:reason` from `disabled-tests.json` and names the production-code seam the refactor must introduce. Leave the `cannot-fail:` skip tag in place so the source-of-truth audit trail stays intact.

The Phase-4 gate refuses to fire while any entry in `disabled-tests.json` is still in the default `pending` state — every entry must resolve to `repair` (done + unskipped) or `defer-to-phase-5` (Story drafted) before the gate is evaluated.

Then, for each Phase-4 child issue in dependency order (from `memory/test-modernize/<slug>/phase-1.md` and `phase-2.md`):

1. Invoke `/build <issue-id-or-path>` — drives RED-GREEN-REFACTOR with inline `/code-review`.
   - For `[Component tests]` Stories created in Phase 2, `/build` is told to bind each test to the specific `<feature-file>::<scenario-name>` pairs cited in the Story's Acceptance Criteria using the binding mode recorded in `phase-0.md` (`bdd-runner` or `xunit-with-annotations`). The Acceptance Criteria checkboxes (one per scenario) must all turn green before the Story closes.
   - For `[Baseline]` Stories (created in Phase 1), tests lock in current behavior at existing seams — no Gherkin binding required.
   - For `[Repair disabled test]` Stories drafted in the pre-flight, `/build` removes the skip tag, lands a real assertion against the cited public-interface behavior, and proves the new assertion can fail.
2. After every Story closes, **extract the Story's production-code file list from `/build`'s commit diff** (`git diff --name-only <story-base-sha>..<story-head-sha>` filtered to production code — test files dropped). The orchestrator MUST NOT consult a tracker CLI for this list; the commit diff is the only source of truth so a tracker JSON-shape change can never silently break the gate.
3. Invoke `/coverage-delta <repo-path> --parent <url-or-empty> --repo-slug <slug> --workflow test-modernize --story <id> --story-files <files-from-step-2>`. Passing `--workflow test-modernize` keeps all memory paths under `memory/test-modernize/` exactly as before. The worker measures and reports; it never halts. Read its stdout result block and act on the `status` field:

   **`status: "ok"` or `"first_measurement"`** — Story closes; advance to the next.

   **`status: "net_new_survivors"`** — pause Story close and surface the halt prompt verbatim:

   ```text
   ⚠ Phase-4 Story <id> close halted — net-new surviving mutants on cited files

   Files this Story claims to test:
     - <file>:<line>  <operator>   <original>  →  <mutated>
     ...

   Actions:
     [s] strengthen — add assertions, then re-run /coverage-delta --workflow test-modernize --story <id> --story-files <files>
     [f] follow-up — open a Phase-5 [Strengthen assertions] Story citing these survivors
     [w] waive    — record reason; survivors carry into Phase 5

   Choose [s/f/w]:
   ```

   - **`s`** — exit the gate; the workflow waits. `/continue` (or re-invoking the same `/coverage-delta` call after the operator strengthens assertions) re-enters at this exact point.
   - **`f`** — draft a Phase-5 `[Strengthen assertions]` Story into `memory/test-modernize/<slug>/phase-5.md`, citing each `file:line:operator` from the result block. Close the current Story and advance.
   - **`w`** — read the operator's reason and append a Phase-4 waiver to `memory/test-modernize/<slug>/waivers.json` tagged with the survivor list. Close the current Story and advance.

   **`status: "tool_unavailable"`** — surface the triage prompt:

   ```text
   Mutation tool unavailable for <language>. Install via /init-dev-team,
   or skip mutation gating for this run.

     [i] install — invoke /init-dev-team and retry the Story close
     [k] skip   — proceed advisory; the rest of Phase 4 runs without
                  mutation gating and Phase 5 is notified
     [q] quit   — halt the workflow

   Choose [i/k/q]:
   ```

4. After all Phase-4 Stories are Done, run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 4` — it cross-checks the scenario → Story-id map against the actually-submitted test code to verify every Scenario has a test citing it.
5. **Review the phase.** Run the loop in `### 3a. Review-the-phase loop`. Specifically:
   - Dispatch `/test-design --since <phase-4-base-sha>` and `/code-review --since <phase-4-base-sha>`.
   - On findings, dispatch `/apply-fixes corrections/`; re-run `/code-review`; loop body capped at **max 2 iterations** before the operator escalation prompt fires.
   - Write the resulting evidence to `memory/test-modernize/<slug>/phase-4-review.json` per the schema in 3a.

**Human gate** — Δ-coverage AND Phase-4 mutation results AND `phase-4-review.json` (any waivers explicit) AND `disabled-tests-resolution.json` (every Phase-3-disabled test resolved to `repair` or `defer-to-phase-5`) accepted before any production-code refactor.

### 5. Refactor-for-testability + converge — `/build` + `/mutation-testing` + `/quality-targets-converge`

For each Phase-5 child issue in dependency order:

1. Confirm the matching `[Baseline]` Story is closed and green (precondition). If not, halt and report.
2. Invoke `/build <issue-id-or-path>` — minimum behavior-preserving refactor + the test that needed the new seam.
   - For `[Component tests]` Stories that landed in Phase 5 (i.e. the surface needed a `[Refactor-for-testability]` first), `/build` binds tests to the cited scenarios using the same binding mode from `phase-0.md`. The matching `[Refactor-for-testability]` Story must be closed and green before any of its dependent `[Component tests]` work starts.
3. After every Story closes, invoke `/mutation-testing <repo-path>` and `/quality-targets-converge <repo-path> --parent <url-or-empty> --repo-slug <slug>`. `/quality-targets-converge` reads `memory/test-modernize/<slug>/mutation-history.json` (written by Phase 4) to avoid re-measuring files Phase 4 already exercised — see that skill's reuse rule.
4. `/quality-targets-converge` loops until all four targets are met or a target is explicitly waived by the operator with the reason recorded on the parent issue / `FEATURE.md`.
5. Run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 5`.
6. **Review the phase.** Run the loop in `### 3a. Review-the-phase loop`. Specifically:
   - Dispatch `/test-design --since <phase-5-base-sha>` and `/code-review --since <phase-5-base-sha>`.
   - On findings, dispatch `/apply-fixes corrections/`; re-run `/code-review`; loop body capped at **max 2 iterations** before the operator escalation prompt fires.
   - Write the resulting evidence to `memory/test-modernize/<slug>/phase-5-review.json` per the schema in 3a.

**Human gate** — final metrics AND `phase-5-review.json` accepted (or each gap waived with reason).

### 6. Report

Report:

- Final coverage %, surviving mutants, determinism status, pre-merge wall-clock.
- The parent issue URL (or `./plans/test-modernize/FEATURE.md` in local-files mode).
- The list of PRs opened by `/build` during Phases 4 + 5.
- Any waived targets with their reasons.

## Notes

- `/test-modernize` is sequencing only — every gate, fix loop, and evidence requirement comes from the underlying skills. If any phase stops at a gate, `/test-modernize` stops with it.
- Resume mid-workflow with `/continue` (which scans `memory/test-modernize/<slug>/phase-<n>.md`) or `/test-modernize <repo> --from-phase <n>`.
- For Phase-1-only analysis without committing to the full workflow, invoke `/cd-test-architecture` directly.
- The workflow is identical whether the operator has a tracker CLI installed or not — only the destination of the issues changes (tracker vs. `./plans/test-modernize/`).
- **Design:** the operator-facing diagram lives at `plugins/dev-team/docs/diagrams/test-modernize-flow.svg` and is embedded in `docs/agent-architecture.md`.
