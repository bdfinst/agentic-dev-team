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
argument-hint: "<repo-path> [--parent <issue-url>] [--ci <path>] [--external-tests <loc>] [--from-phase <n>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill(cd-test-architecture *), Skill(issues-from-assessment *), Skill(gherkin-public *), Skill(test-audit-disable *), Skill(coverage-baseline *), Skill(coverage-delta *), Skill(quality-targets-converge *), Skill(build *), Skill(mutation-testing *)
---

# Test Modernize

Role: orchestrator. This command sequences existing skills/agents through the five-phase legacy-test-modernization workflow; it does not implement, audit, or write tests itself. Each phase is delegated to the worker skill that owns it, the workflow gates on human approval between phases, and per-phase progress is persisted to `memory/test-modernize/<repo>/phase-<n>.md` so `/continue` (and `--from-phase`) can resume.

You have been invoked with the `/test-modernize` command.

## Orchestrator constraints

1. **Delegate every phase.** Call the owning skill or agent (`/cd-test-architecture`, `/issues-from-assessment`, `/gherkin-public`, `/test-audit-disable`, `/coverage-baseline`, `/build`, `/coverage-delta`, `/mutation-testing`, `/quality-targets-converge`, `dev-team:test-modernization-review`); do not re-implement their logic here.
2. **Honor the human gates.** Do not advance past a gate without explicit approval — this command sequences phases, it does not remove their review points.
3. **Confirm the approach first.** Surface every ambiguous input (repo path, parent issue URL, CI config, external test sources, quality targets) in a single batch before Phase 1 starts.
4. **Be concise.** Report each phase's outcome and the next gate, nothing more.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>` (required) — the legacy repo under modernization.
- `--parent <issue-url>` — parent issue URL on ADO / GitHub / GitLab / Jira. Empty or omitted → local-files mode.
- `--ci <path>` — existing pipeline config (azure-pipelines.yml / .github/workflows / Jenkinsfile). Passed through to `/cd-test-architecture`.
- `--external-tests <loc>` — other-repo suites, Postman collections, manual scripts. Passed through to `/cd-test-architecture`.
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
7. Generate a `<repo-slug>` (last path segment, lowercased, non-alphanumerics → `-`). All progress files live under `memory/test-modernize/<repo-slug>/`.

Print the resolved inputs (sink, CLI, fallback decision, targets, `<repo-slug>`) and proceed. If `--from-phase <n>` was given, jump to that phase.

### 1. Analyze — `/cd-test-architecture` + `/issues-from-assessment`

1. Invoke `/cd-test-architecture <repo-path> [--ci <ci-path>] [--external-tests <loc>]`. It writes the assessment to `reports/cd-test-architecture-<app>.md`.
2. Invoke `/issues-from-assessment <assessment-path> --parent <url-or-empty> --repo-slug <slug>`. It creates the parent + Phase-1 / Phase-2 / Phase-5 children via the resolved CLI (or local plan files) and writes a per-phase index to `memory/test-modernize/<slug>/phase-1.md`.
3. Dispatch `dev-team:test-modernization-review` (Agent tool) with `--phase 1`. Surface any blocker findings to the operator and have them resolved before the gate.

**Human gate** — wait for approval before specifying the public interface.

### 2. Specify public interface — `/gherkin-public`

1. Invoke `/gherkin-public <repo-path> --repo-slug <slug>`. It reads the component map from `memory/test-modernize/<slug>/phase-1.md` and writes `.feature` files per public surface (API endpoint, UI flow, batch-job entry point, library export, event type) to `features/test-modernize/` (or `./specs/test-modernize/` if no `features/` dir exists).
2. Dispatch `dev-team:test-modernization-review --phase 2`.

**Human gate** — operator validates the Gherkin scenarios before any test changes land. This is a hard stop.

### 3. Audit + baseline coverage — `/test-audit-disable` + `/coverage-baseline`

1. Invoke `/test-audit-disable <repo-path> --repo-slug <slug>`. Disables every cannot-fail test (skip + tag, never delete) and records reasons in `memory/test-modernize/<slug>/disabled-tests.json`.
2. Invoke `/coverage-baseline <repo-path> --parent <url-or-empty> --repo-slug <slug>`. Runs the project's coverage tool, records the baseline at `memory/test-modernize/<slug>/baseline-coverage.json`, and posts the number to the parent issue (or `./plans/test-modernize/FEATURE.md` in local-files mode).
3. Dispatch `dev-team:test-modernization-review --phase 3`.

**Human gate** — baseline accepted before adding tests.

### 4. Fix disabled tests + add no-refactor tests — `/build` + `/coverage-delta`

For each Phase-4 child issue in dependency order (from `memory/test-modernize/<slug>/phase-1.md`):

1. Invoke `/build <issue-id-or-path>` — drives RED-GREEN-REFACTOR with inline `/code-review`.
2. After every Story closes, invoke `/coverage-delta <repo-path> --parent <url-or-empty> --repo-slug <slug>`. Posts Δ vs. baseline to the parent issue / `FEATURE.md`.
3. After all Phase-4 Stories are Done, dispatch `dev-team:test-modernization-review --phase 4`.

**Human gate** — Δ-coverage accepted before any production-code refactor.

### 5. Refactor-for-testability + converge — `/build` + `/mutation-testing` + `/quality-targets-converge`

For each Phase-5 child issue in dependency order:

1. Confirm the matching `[Baseline]` Story is closed and green (precondition). If not, halt and report.
2. Invoke `/build <issue-id-or-path>` — minimum behavior-preserving refactor + the test that needed the new seam.
3. After every Story closes, invoke `/mutation-testing <repo-path>` and `/quality-targets-converge <repo-path> --parent <url-or-empty> --repo-slug <slug>`.
4. `/quality-targets-converge` loops until all four targets are met or a target is explicitly waived by the operator with the reason recorded on the parent issue / `FEATURE.md`.
5. Dispatch `dev-team:test-modernization-review --phase 5`.

**Human gate** — final metrics accepted (or each gap waived with reason).

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
- **Design:** see `docs/specs/legacy-test-modernization-workflow-design.md` for the rationale behind the five-phase order of operations, the *baseline-before-refactor* invariant, the *airplane test*, and the direct-CLI-dispatch decision (no shell-adapter library). The operator-facing diagram lives at `plugins/dev-team/docs/diagrams/test-modernize-flow.svg` and is embedded in `docs/agent-architecture.md`.
