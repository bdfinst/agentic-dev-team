---
name: issues-from-assessment
description: >-
  Convert a `/cd-test-architecture` assessment into a parent + Phase-tagged
  child issues on the tracker the operator points at (ADO, GitHub, GitLab,
  Jira). Dispatches by parent URL host to the tracker's own CLI (`az boards`,
  `gh`, `glab`, `acli`). When no parent URL is given, or when the required
  CLI is not installed, falls back to local plan files under
  `.claude/plans/<workflow>/` after informing the operator. Multi-workflow: called
  by `/test-improve` (Phase 4), via its own
  `--workflow` namespace so memory paths and tracker labels never collide.
argument-hint: "<assessment-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>] [--refactor-mode <no-refactor|refactor-allowed>] [--dry-run]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Issues from Assessment

Role: worker. Converts the assessment produced by `/cd-test-architecture` into the tracker artifacts the calling test-improvement workflow expects (Feature/Epic + Phase-tagged Stories + Tasks with predecessor links), or — when no tracker CLI is available — into local plan files with the same structure. Lifts the preview-then-confirm + `gh issue create` patterns from `/issues-from-plan`.

You have been invoked with the `/issues-from-assessment` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<assessment-path>` — the file `/cd-test-architecture` wrote (`.dev-team-reports/cd-test-architecture-<app>.md`).
- `--parent <issue-url>` — parent issue / Feature / Epic URL. Empty or omitted → local-files mode.
- `--repo-slug <slug>` — slug used for the `.claude/memory/<workflow>/<slug>/` namespace. Defaults to the assessment file's `<app>` token.
- `--workflow <name>` — the workflow namespace under `.claude/memory/` and `.claude/plans/`, and the leading tracker-label token. Defaults to `test-improve`. Callers pass their own namespace so parallel runs stay quarantined.
- `--refactor-mode <no-refactor|refactor-allowed>` — optional; the caller's Phase-0 refactor choice. Defaults to `refactor-allowed` (unchanged behavior) when omitted. When `no-refactor`, the Phase-5 `[Refactor-for-testability]` work is emitted as **out-of-scope / skipped-in-no-refactor** plan entries — informational context only, **never actionable Stories** — so the written plan shows the coverage/behavior left on the table without offering refactor work this run will not do.
- `--dry-run` — print the preview list and exit without creating anything.

If `<assessment-path>` is absent or the file is missing, ask the operator to point at one.

**Path + label templates.** Every filesystem path and every operator-visible tracker label in the Steps below carries `<workflow>` as a placeholder — the skill interpolates the resolved `--workflow` value at run time. No literal workflow name appears in a path or label string.

## Steps

### 1. Resolve sink (host-based dispatch + CLI probe)

Parse the `--parent` URL host. Pick the CLI and probe it:

| Host pattern | CLI | Probe |
|---|---|---|
| `dev.azure.com` | `az` (with `az boards` extension) | `command -v az >/dev/null 2>&1 && az extension show -n azure-devops >/dev/null 2>&1` |
| `github.com` | `gh` | `command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1` |
| `*.atlassian.net` | `acli` (Atlassian CLI) | `command -v acli >/dev/null 2>&1` — if missing, try REST with `$JIRA_TOKEN` |
| `gitlab.com` / self-hosted GitLab | `glab` | `command -v glab >/dev/null 2>&1 && glab auth status >/dev/null 2>&1` |
| *empty / omitted* | (none) | local-files mode |

**If the probe fails**, tell the operator exactly what's missing and the canonical install / auth command, then fall back to local-files mode automatically. Example:

```
gh is not installed. Run `/project-init` to set up this repo's tooling, or install
gh directly from https://cli.github.com/ and run `gh auth login`.
Falling back to local-files mode — Stories will be written to .claude/plans/<workflow>/.
```

Record the resolved sink in `.claude/memory/<workflow>/<slug>/phase-1.md` so subsequent workers (`/coverage-baseline`, `/coverage-delta`, `/quality-targets-converge`) reuse the same dispatch decision.

### 2. Read the assessment + derive children

Parse the assessment file's sections per `/cd-test-architecture`'s contract:

- **Components & patterns** → Feature description.
- **Current-vs-correct test classification** → input to Phase-5 `[Re-scope]` Stories.
- **Duplicate-coverage table** → Phase-5 `[De-duplicate]` Stories.
- **CD-fitness gaps** → Phase-1 `[Gap]` Stories.
- **Seam-reachability table per component** → Phase-4 `[Baseline]` Stories + Phase-5 `[Refactor-for-testability]` Stories. When `--refactor-mode no-refactor`, the `[Refactor-for-testability]` entries are emitted **out-of-scope (skipped-in-no-refactor)** — listed for visibility, not created as actionable Stories.
- **Target architecture (per component)** → Phase-5 Stories per (component, layer) **EXCLUDING `[Component tests]`** — those Stories are created by `/gherkin-public` at the end of Phase 2, bound to the approved Gherkin scenarios.

`[Component tests]` Stories are intentionally NOT created from the assessment. Creating them here would bind the test code to the *recommended* behavior in the assessment rather than the *approved* behavior in the Gherkin — and the Phase-2 human gate exists precisely to let the operator sharpen, add to, or correct the inferred behaviors before any test binds to them. `/gherkin-public --create-stories` produces them after the gate.

For each derived child, build the title + body + phase-tag + predecessor list per the prompt's "ADO mapping" section in `reports/legacy-test-modernization-prompt.md`. The phase tags are `Phase-1` through `Phase-5`. Predecessor links follow the rules:

- Every `[Baseline]` blocked by `[Audit]` (created in Phase 3, referenced by ID).
- Every `[Refactor-for-testability]` blocked by the matching `[Baseline]`.
- Every contract / integration / E2E / resilience Story blocked by the same component's `[Component tests]` (those IDs are filled in by `/gherkin-public` in Phase 2; this skill leaves a placeholder `Depends on: [Component tests] for <component> (created in Phase 2)` and the orchestrator backfills the link after Phase 2).
- Every `[De-duplicate]` blocked by the Story that adds the kept-layer test.
- Every `[Re-scope]` blocked by the Story that lands the test at the correct layer.

### 3. Preview + confirm

Print the full list (titles, types, predecessors, one-line acceptance summary) — grouped by phase. Ask:

> Create these N issues against `<parent or local-files>`? (yes / no / dry-run output only)

Do not call any tracker CLI or write any plan files until the operator answers `yes`. If `--dry-run` was given, print the list and exit zero.

### 4. Create the parent (tracker mode only)

If `--parent <url>` was provided, the parent already exists — capture its ID/number from the URL. Otherwise (local-files mode), create the parent **file**:

```
.claude/plans/<workflow>/FEATURE.md
```

Contents: the assessment summary (components table, target pre-merge gate, link to the MinimumCD component-test page), plus a placeholder block for running metric snapshots that `/coverage-baseline`, `/coverage-delta`, and `/quality-targets-converge` will append to.

### 5. Create the children — partial-failure safe

Two modes share the same control flow; only the create-call differs. Every tracker label carries `<workflow>` as its leading token so an operator scanning a mixed board can tell which workflow authored an issue.

**Tracker mode.** For each child in dependency order, call the resolved CLI. Lift the GitHub pattern verbatim from `/issues-from-plan`, **including its Conventional Commit title rule** — GitHub is the only tracker here bound to `commitlint.config.js`/`issue-title-lint.yml`; ADO/GitLab/Jira titles keep the plain `[<phase-tag>] <component>` form from step 2 unchanged. For GitHub, prefix that same phase-tag title with a type — `test:` fits every phase here (audit/baseline/refactor-for-testability/de-duplicate/re-scope are all test-suite work): `test: [Baseline] <component>`. Verify with `printf '%s' "<title>" | npx commitlint --verbose` before creating.

```bash
# GitHub — github.com
gh issue create --title "test: [<phase-tag>] <title>" --body "$(cat <<'EOF'
## What to Build

<one-paragraph behavior description>

Part of #<parent>

## Phase

Phase-<n>

## Depends On

- #<predecessor>: <reason>   <!-- "none" if no predecessors -->

## Acceptance Criteria

- [ ] <gherkin scenario 1>
- [ ] <gherkin scenario 2>

## Architectural Context

<assessment excerpt for this row>

## Testing Approach

<which test layer, which doubles, which pipeline stage>
EOF
)" --label "<workflow>,phase-<n>,<minimumcd-type>"
```

For the other trackers:

```bash
# Azure DevOps — dev.azure.com
az boards work-item create \
  --org "https://dev.azure.com/<org>" --project "<project>" \
  --type "User Story" --title "<title>" \
  --description "<body>" \
  --fields "Microsoft.VSTS.Common.AcceptanceCriteria=<gherkin>" \
           "System.Tags=<workflow>; phase-<n>; <minimumcd-type>"
# Then `az boards work-item relation add` for parent + predecessor links.

# GitLab — gitlab.com / self-hosted
glab issue create --title "<title>" --description "<body>" \
  --label "<workflow>,phase-<n>,<minimumcd-type>" \
  --linked-mr none
# Predecessor links via `glab issue note add` referencing #<id>.

# Jira — *.atlassian.net
acli jira workitem create --type Story --summary "<title>" \
  --description "<body>" \
  --label "<workflow>" --label "phase-<n>" --label "<minimumcd-type>"
# Parent + `is blocked by` links via `acli jira workitem link`.
```

Record the **child-slug → tracker-id** map as you go (in `.claude/memory/<workflow>/<slug>/issue-map.json`).

**Local-files mode.** Write one `.claude/plans/<workflow>/phase-<n>/<child-slug>.md` per child. The file's body holds the same fields the tracker would (Phase, Depends On, Acceptance Criteria, Architectural Context, Testing Approach). Cross-Story predecessor links use **relative paths** (e.g. `Blocked by: ../phase-4/baseline-orders-api.md`). A `Status:` line at the top defaults to `Open` and gets flipped to `Done: <date>` by `/coverage-delta` and `/quality-targets-converge` when the matching gate passes.

**Partial-failure safety.** If any CLI call (or file write) fails partway, do **not** abort silently. Report:

- Which children were created (with IDs / paths).
- Which were not.
- The first failure's stderr.

Leave the partial state on disk and let the operator decide whether to resume.

### 6. Backfill predecessor links

For tracker mode, after every child exists, walk the child-slug → tracker-id map and add the predecessor links:

- GitHub: append `Depends on #<n>` lines to the body, or use `gh issue edit` to update the issue.
- ADO: `az boards work-item relation add --relation-type "System.LinkTypes.Dependency-Reverse" --id <child> --target-id <predecessor>`.
- GitLab: `glab issue note add <child-iid> --message "Depends on #<predecessor>"`.
- Jira: `acli jira workitem link --inward "is blocked by" --from <child> --to <predecessor>`.

For local-files mode, the `Blocked by:` lines were written in Step 5 — no backfill needed.

### 7. Persist phase-1 progress

Write `.claude/memory/<workflow>/<slug>/phase-1.md` with:

- Resolved sink (CLI + parent URL or `local-files`).
- Phase counts per phase tag.
- The child-slug → tracker-id (or relative path) map.
- The assessment file path.
- Quality targets in force.

### 8. Report

Print:

- Parent: `<URL>` or `.claude/plans/<workflow>/FEATURE.md`.
- N children created across Phases 1, 2, 4, 5 (Phase-3 Stories are created by `/test-audit-disable` + `/coverage-baseline` later).
- Any partial-failure messages from Step 5.
- The path to `.claude/memory/<workflow>/<slug>/phase-1.md` for `/continue`.

## Examples / Integration

- `/test-improve` invokes this worker with `--workflow test-improve` from its Phase 4; paths resolve under `.claude/memory/test-improve/<slug>/` and labels lead with `test-improve`.
- `/test-improve` invokes this worker with `--workflow test-improve`; paths resolve under `.claude/memory/test-improve/<slug>/` and labels lead with `test-improve`, keeping a mixed board unambiguous when both workflows are active.

## Notes

- This worker is the only place tracker-CLI knowledge sits. Adding a new tracker means one new branch in Steps 1 + 5; no other skill changes.
- `/issues-from-plan` (the existing GitHub-only issue creator) handles a *plan*; this worker handles a *test-architecture assessment*. The two are intentionally separate — overlap is only the `gh issue create` snippet.
- Adding a new workflow caller means passing a new `--workflow <name>` value; no path or label edits inside this skill are required because both are templated.
