---
name: system-test-design
description: Test design for a distributed system — an entry-point deployable plus the deployables it calls or that call it. Triage existing E2E tests (KEEP / PUSH DOWN / DELETE), find the minimum E2E set and gaps, spot entangled workflows, pair overlapping tests across layers using coverage and mutation evidence, and validate test doubles. Use when the user asks "which E2Es do we need", "are we over-testing", "which tests duplicate a cheaper layer", "is this entangled with service X", or "what is our minimum E2E set". Advisory — writes a report, does not edit tests.
role: worker
user-invocable: true
argument-hint: "<entry-repo> [related-repo...] [--coverage <repo>=<path>]... [--mutation <repo>=<path>]... [--aliases <path>] [--e2e-only] [--overlap-only]"
allowed-tools: >-
  Read, Write, Grep, Glob, mcp__codegraph__*,
  mcp__plugin_repowise_repowise__get_overview,
  mcp__plugin_repowise_repowise__search_codebase,
  mcp__plugin_repowise_repowise__get_context,
  mcp__plugin_repowise_repowise__get_answer,
  Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/system_test_design_args.py" *,
       python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_evidence_detect.py" *,
       python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_report_grader.py" *,
       git rev-parse *)
---

# System Test Design

Role: worker. Assesses and reports across several repositories. It does not edit, move, or delete any test; fixes go to `/plan` or `/build`.

## Overview

The system-level altitude: `test-health` audits one suite's strategy, `cd-test-architecture` one application, `test-design-advisor` one unit. This skill covers an **entry-point deployable plus the deployables it calls or that call it**. It combines four capabilities: E2E triage and the minimum E2E set; cross-layer overlap; the system map with entangled workflows; ownership and test-double validation.

Cite, never restate, these knowledge files:

- `knowledge/cd-test-architecture.md` — six test types, the E2E Justification Gate, E2E candidate criteria, taxonomy, placement, the overlap resolution rule.
- `knowledge/test-layer-ownership.md` — in/out of band, the ownership decision, duplication checks, removal rule, antipatterns.
- `knowledge/entangled-workflows.md` — the three kinds, their signs, guarding E2E, decoupling step.
- `knowledge/microservice-testing.md` — contract test checks.

## Constraints

- Advisory only. Output is recommendations; the report ends `Recommendations only; no tests were changed.`
- MinimumCD six types throughout. "Contract test" is primary.
- The E2E gate stays canonical in `cd-test-architecture.md`; do not restate its four conditions.
- **No per-layer count target and no current-vs-recommended shape table, anywhere.** Descriptive counts in *Current test architecture* are allowed. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_report_grader.py" count-targets <report>` checks this mechanically.
- E2E is never a pre-merge gate. Every KEEP journey and candidate names a stage: post-deploy, scheduled, acceptance-in-ephemeral-env, or synthetic monitoring.
- Never require coverage or mutation tooling. Unusable evidence falls back to static judgment and says why.
- Do not test consumed services; test parsing of the fields used and the response when the dependency is slow, unavailable, or wrong.
- Never guess behavior of a deployable that is not available: list it as an external boundary under Open questions.
- Every finding cites `path:line` or a test name and is labelled `observed` or `inferred`.

## Parse Arguments

Run the validator first. It prints the resolved run as JSON, or one error line and exit 2:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/system_test_design_args.py" <the user's arguments>
```

On exit 2, **stop before writing any file**, tell the user the error, and do nothing else. Errors: a repo path that does not exist or is not a git checkout; a `<repo>=` value naming a repo not in scope; both mode flags; no entry repo. `<repo>` in `--coverage`/`--mutation` is a repo basename. Use the JSON's `mode`, `repos`, `coverage`, `mutation`, `aliases`, and `report_path`.

**Repo set:** the named repos plus every repowise-indexed repo the entry repo references (producer/consumer, client, topic, queue, endpoint — via `search_codebase` and `get_context include=["references"]`). Discovered repos are read and listed in Scope as `discovered`. A referenced deployable with no index and no named path is `not scanned`.

## Discovery order

repowise first (`get_overview` per repo, then `search_codebase`, `get_context`, `get_answer`), then CodeGraph, then Grep/Read. A repo whose `get_overview` fails or reports no index is **unindexed**: the report names it and says to run `repowise init --yes --no-prose`; continue with Grep/Read for it. If the repowise MCP is absent, every repo is unindexed, discovery of unnamed repos is skipped, and the report says so once.

## Steps

`--e2e-only` runs 1, 2, 5, 6, 7. `--overlap-only` runs 2, 3, 4, 7. No flag runs all.

1. **System map.** Entry points, outbound dependencies, interface definitions, config wiring, and entangled workflows per `knowledge/entangled-workflows.md`.
2. **Test inventory.** Classify every test by what is real and what is doubled, never by folder or name. Record CI stage and whether it blocks merge or deploy. Detect CI as `test-health` does: `.github/workflows`, `.gitlab-ci.yml`, `azure-pipelines.yml`, else `stage: unknown`. Build the test-double validation table: double, contract test, integration test (a missing one is a finding).
3. **Behavior inventory** with the owning test type, by the ownership decision in `knowledge/test-layer-ownership.md`.
4. **Overlap and misplacement.** [`references/layer-overlap.md`](references/layer-overlap.md). Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_evidence_detect.py" --kind <coverage|mutation> <path>` for each evidence path to get the format or the exact reason.
5. **Existing-E2E triage.** [`references/e2e-triage.md`](references/e2e-triage.md).
6. **E2E candidates and rejections.** Candidate criteria, ranking, and placement per `cd-test-architecture.md`; gap discovery per `references/e2e-triage.md`.
7. **Report.** Write `report_path` (`.dev-team-reports/system-test-design-<entry>.md` in the invoking directory; overwrite a prior report of the same name) using [`references/report-template.md`](references/report-template.md). Then run the count-target check on it.

Contract-test findings (`knowledge/microservice-testing.md`, Contract test checks) and *Test improvements* (antipatterns from `test-layer-ownership.md`) derive from step 2 and 3.

Stack hints: .NET component tests often use `WebApplicationFactory<TEntryPoint>` with Testcontainers or WireMock.Net and contract tests PactNet; in Azure DevOps read `azure-pipelines.yml` and its templates for test stages, scheduled triggers, contract publishing, and deploy gates such as Pact `can-i-deploy`. For other stacks identify the equivalent test hosts, container helpers, virtual services, and contract libraries before classifying.

## Integration

- `test-health` invokes this skill for a multi-deployable target and summarizes its minimum E2E set and overlap findings.
- One application: `cd-test-architecture`. One unit: `test-design-advisor`. Per-file smells, including the four layer smells: `test-smell-review`.
- Hand fixes to `/plan` or `/build`.
