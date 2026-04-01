# Upgrade Plan: Competitive Gaps from Kodus AI Analysis

**Source**: `reports/competitive-analysis-2026-04-01-kodus-ai.md`
**Date**: 2026-04-01

This document distills the competitive analysis against [Kodus AI](https://github.com/kodustech/kodus-ai) into an actionable upgrade plan. It covers only the gaps and weaknesses — for the full comparison (including our strengths and areas where we're ahead), see the source report.

---

## Priority 1: Plain-Language Custom Review Rules

**Classification**: Missing | **Complexity**: Small | **Layer**: Knowledge

### Problem

Users cannot define project-specific review criteria without editing agent source files. Kodus lets users write rules in natural language ("All API handlers must validate input using zod schemas") and auto-imports standards from `.cursorrules`, `.github/copilot-instructions.md`, and similar config files.

Our existing `REVIEW-CONTEXT.md` provides unstructured context but lacks a schema, severity levels, or scoping — making it unreliable as a rules mechanism.

### Proposed Changes

**New file**: `knowledge/custom-review-rules.md` (user-editable per project, not shipped with the plugin)

Schema:

```markdown
# Custom Review Rules

## Rules

- severity: error | scope: src/api/** | All API route handlers must validate request bodies with zod
- severity: warn | scope: **/*.ts | Prefer `readonly` arrays in function signatures
- severity: info | scope: src/domain/** | Domain entities must not import from infrastructure layer
```

**Modified file**: `commands/code-review.md`

- Before dispatching review agents, check for `custom-review-rules.md` (or a configured path) in the project root
- Parse rules and inject them into each review agent's prompt as additional review criteria
- Also scan for and auto-import rules from:
  - `.cursorrules`
  - `.github/copilot-instructions.md`
  - `.claude/CLAUDE.md` (extract any review-relevant directives)

**Modified files**: All review agent definitions in `agents/`

- Add a standard section to the agent prompt template: "If custom review rules are provided, evaluate each rule within your domain of expertise and report violations using the rule's specified severity."

### Acceptance Criteria

- [ ] User can create a `custom-review-rules.md` with plain-language rules
- [ ] `/code-review` loads and distributes rules to review agents
- [ ] Rules with `scope` patterns are only checked against matching files
- [ ] Rules from `.cursorrules` are auto-imported when the file exists
- [ ] Review output includes custom rule violations with the specified severity

---

## Priority 2: PR Inline Comment Integration

**Classification**: Weaker | **Complexity**: Medium | **Layer**: Command

### Problem

Review results stay local — written to files or displayed in chat. Teammates reviewing a PR in the GitHub UI never see our findings unless the author manually copies them. Kodus posts findings as inline PR comments directly on the diff.

### Proposed Changes

**New file**: `skills/pr-comment-integration.md`

Defines the mapping from review agent output to GitHub PR review comments:

- Each finding must include `file`, `line`, and `body`
- Findings map to `gh api` calls: `POST /repos/{owner}/{repo}/pulls/{pr}/comments`
- Batch all comments into a single review using the GitHub "pull request review" API (create review → add comments → submit review)
- Only post FAIL and WARN severity findings
- Include the agent name in each comment for traceability

**Modified file**: `commands/code-review.md`

- Add `--post-to-pr` flag
- When flag is set, after aggregating findings, invoke the PR comment skill
- Detect the current PR number from `gh pr view --json number` or accept it as an argument

**Prerequisite audit**: Review agents must consistently output `file:line` references. Audit all 19 agents and standardize output format where inconsistent.

### Acceptance Criteria

- [ ] `/code-review --post-to-pr` posts findings as inline GitHub PR comments
- [ ] Comments appear on the correct file and line in the PR diff
- [ ] Each comment identifies which review agent produced the finding
- [ ] Only FAIL and WARN findings are posted (INFO stays local)
- [ ] Works with `gh` CLI authentication (no additional auth setup)
- [ ] Graceful failure if no PR exists for the current branch

---

## Priority 3: Static Analysis Pipeline Integration

**Classification**: Weaker | **Complexity**: Medium | **Layer**: Skill

### Problem

All code analysis is LLM-based. Syntactic issues (unused variables, unreachable code, type errors) that a parser handles deterministically are instead caught (or missed) by the LLM. Kodus uses AST-based analysis alongside LLM review, reducing noise on syntactic checks.

We already have `/semgrep-analyze` but it's a standalone command — not wired into the `/code-review` pipeline.

### Proposed Changes

**New file**: `skills/static-analysis-integration.md`

Defines a pre-pass stage for `/code-review`:

1. Detect available static analysis tools (Semgrep, ESLint, TypeScript compiler, pylint, etc.)
2. Run applicable tools against the target files
3. Parse structured output (SARIF, JSON, or tool-specific formats)
4. Deduplicate findings across tools
5. Pass structured findings to review agents as "confirmed issues" — agents can reference them without re-detecting, and focus LLM reasoning on semantic concerns

**Modified file**: `commands/code-review.md`

- Add an optional static analysis pre-pass before dispatching review agents
- Controlled by `--static-analysis` flag (or auto-detected when tools are available)
- Feed tool output as structured context to agents: "The following issues were detected by static analysis tools. Do not re-report these. Focus your review on semantic and architectural concerns."

**Modified file**: `commands/semgrep-analyze.md`

- Refactor to support being called programmatically (returning structured data) in addition to standalone use

### Acceptance Criteria

- [ ] `/code-review --static-analysis` runs Semgrep (if installed) before dispatching agents
- [ ] Static analysis findings are passed to review agents as pre-confirmed context
- [ ] Review agents do not duplicate findings already caught by static analysis
- [ ] Pipeline gracefully skips static analysis if no tools are installed
- [ ] ESLint integration works for JS/TS projects when ESLint is configured

---

## Priority 4: Automated Learning from PR History

**Classification**: Weaker | **Complexity**: Large | **Layer**: Skill

### Problem

Our Feedback & Learning skill requires explicit user triggers (`amend`, `learn`, `remember`, `forget`). No passive learning occurs. Kodus auto-learns team conventions from historical PRs and merged code, adapting review behavior over time.

### Proposed Changes

**New file**: `skills/pattern-learning.md`

Phased approach:

**Phase A — Pattern Extraction** (ship first):
1. Command `/learn-patterns` analyzes the last N merged PRs (default 20)
2. Extracts recurring patterns: naming conventions, file organization, import patterns, test structure, error handling approaches
3. Generates candidate rules in the same format as `custom-review-rules.md`
4. Presents candidates to the user for approval — no automatic activation
5. Approved rules are appended to `knowledge/learned-patterns.md`

**Phase B — Continuous Learning** (ship later):
1. After each `/code-review` run, compare findings against merged code to detect false positives
2. After each PR merge, compare the merged code against review findings to detect missed issues
3. Surface pattern drift to the user periodically

**New file**: `knowledge/learned-patterns.md` (auto-generated, user-editable)

Same schema as `custom-review-rules.md` but populated by the learning skill rather than manually.

**Modified file**: `commands/code-review.md`

- Load `learned-patterns.md` alongside `custom-review-rules.md` when distributing context to agents

### Acceptance Criteria

**Phase A**:
- [ ] `/learn-patterns` analyzes recent merged PRs and extracts candidate rules
- [ ] Candidates are presented to the user for approval before activation
- [ ] Approved patterns are stored in `knowledge/learned-patterns.md`
- [ ] `/code-review` loads learned patterns as additional review context

**Phase B** (deferred):
- [ ] False positive detection from merged code vs. review findings
- [ ] Periodic pattern drift reports

---

## Priority 5: DORA / Engineering Metrics

**Classification**: Missing | **Complexity**: Medium | **Layer**: Skill

### Problem

No engineering performance metrics beyond raw task logs in `metrics/`. Kodus provides a web dashboard with DORA metrics (deployment frequency, cycle time), PR analytics, and bug ratios.

### Proposed Changes

**New file**: `skills/engineering-metrics.md`

Compute DORA metrics from Git history (no external service needed):

| Metric | Source |
|--------|--------|
| Deployment frequency | Tags/releases per time period |
| Lead time for changes | First commit to merge (per PR) |
| Change failure rate | Reverted PRs / total merged PRs |
| Mean time to recovery | Time between revert-triggering merge and fix merge |

**New file**: `commands/metrics-report.md`

- `/metrics-report` generates a markdown report in `reports/metrics-<date>.md`
- Covers last 30 days by default, configurable with `--since` and `--until`
- Includes trends if previous reports exist

**Modified file**: `skills/performance-metrics.md`

- Add estimated token cost tracking per review run, using published model pricing
- Include cost breakdown in `/review-summary` output

### Acceptance Criteria

- [ ] `/metrics-report` generates a DORA metrics report from Git history
- [ ] Report includes deployment frequency, lead time, change failure rate, MTTR
- [ ] Report includes trend comparison against previous report (if exists)
- [ ] Token cost estimates appear in `/review-summary` output

---

## Deferred Items

These gaps were identified but are not prioritized for immediate work:

| Gap | Why Deferred |
|-----|-------------|
| GitLab / Bitbucket / Azure DevOps support | Claude Code user base is predominantly GitHub. Revisit if demand signals change. |
| SOC 2 compliance | Compliance certification is a business decision, not a plugin feature. |
| Model agnosticism | Claude Code is Anthropic-native. Model flexibility is architecturally constrained by the host platform. |
| Web dashboard | Contradicts local-first philosophy. Markdown reports serve the same analytical need without infrastructure. |
| Multi-user team management | Single-user CLI plugin by design. Team coordination happens in Git, not in the plugin. |

---

## Implementation Sequence

```
Priority 1 (Small)     Priority 2 (Medium)      Priority 3 (Medium)
Custom Review Rules --> PR Comment Integration --> Static Analysis Integration
       |                                                    |
       v                                                    v
Priority 4, Phase A (Medium)                    Priority 5 (Medium)
Pattern Learning (extraction)                   DORA Metrics Report
       |
       v
Priority 4, Phase B (Large)
Pattern Learning (continuous)
```

Priorities 1-3 form a natural chain: define rules, make findings visible in PRs, add deterministic analysis. Priority 4 Phase A can run in parallel with Priority 3. Priority 5 is independent and can slot in whenever capacity allows.

### Estimated Effort

| Priority | Sessions | Dependencies |
|----------|----------|-------------|
| 1. Custom review rules | 1 | None |
| 2. PR comment integration | 1-2 | Agent output format audit |
| 3. Static analysis integration | 1-2 | Semgrep refactor |
| 4a. Pattern learning (extraction) | 2-3 | Priority 1 (shared rule format) |
| 4b. Pattern learning (continuous) | 3-4 | Priority 4a |
| 5. DORA metrics | 1-2 | None |
