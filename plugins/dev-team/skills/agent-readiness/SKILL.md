---
name: agent-readiness
description: >-
  Score how ready the current repository is for AI-assisted development against
  the Agent-Readiness Scorecard. Use when the user asks "how agent-ready is this
  repo", "score this repo for agents", "agent readiness", or wants a tiered
  readiness report. Scores YOUR project repo's readiness — not the dev-team
  plugin's own review agents and routing (for that, use /harness-audit).
argument-hint: "[repo-path] [--json <file>] [--markdown <file>]"
user-invocable: true
allowed-tools: >-
  Bash(python3 *), Read, Glob
---

# Agent-Readiness Scanner (MVP)

Role: worker. Scores a **single local repository** against the Agent-Readiness
Scorecard and reports a tier (Agent-Ready / Assisted / Limited / Hostile) with
per-criterion evidence.

> **Not `/harness-audit`.** This scores the **subject repository** (your
> project's build, code quality, docs, and version-control hygiene) from a
> static checkout. `/harness-audit` audits the **dev-team plugin's own harness**
> (review-agent effectiveness, model tiers, orchestration) from accumulated
> runtime metrics. Different subject, different input, different output.

## Scope (MVP — issue #117)

This MVP uses **file-presence/heuristic analyzers only** — no CI-platform APIs.
It scores the criteria that can be judged from a checkout:

- **Build & Env:** B2 reproducible env, B3 dependency lock files, B5 composite check command
- **Code Quality:** C1 formatting, C2 linting, C4 module size (p90 line count)
- **Documentation:** D1 README, D2 AI instructions, D3 architecture docs,
  D5 CLAUDE.md size, D6 layered context
- **Version Control:** V2 pre-commit hooks, V3 commit conventions, V4 dep scanning

D5, D6, B5 (and the manual-review-only D7) implement the AI-friendly repository
rubric in [`knowledge/ai-friendly-repo-guidelines.md`](../../knowledge/ai-friendly-repo-guidelines.md),
the canonical source for the rationale; evidence strings link to its anchors.
Colocated-test and directory-depth criteria are a deferred follow-up.

**Score shift (scorecard 1.1-mvp).** Adding D5, D6 and B5 changes the
documentation and build_env category percentages, and so the renormalized
overall score, for repos scanned before this version. The shift is accepted;
tier thresholds are unchanged. Compare scores only within one scorecard
version (`scanner_version` in the JSON).

Criteria that need CI-platform data (coverage, flaky rate, durations, branch
policy — T1–T5, B1, B4, C5, S1–S4, V1) and the org-scale Azure DevOps / Jenkins
discovery from the original plan are **deferred** to follow-up phases.
Categories with no MVP criterion (test infrastructure, type safety) are reported
as `deferred` and excluded from the renormalized overall score.

## Evidence table

Each scored criterion emits `score` (0-2), `max`, and an `evidence` string. The
new criteria use `found X; threshold Y; to fix: Z (see <guide>#anchor)`.
N/A results (`max` 0, e.g. D5 when no AI-instructions file exists; see D2) are
exempt: they carry a plain-text reason and add nothing to the category score.

| Criterion | Category | Scores on | Threshold (scorecard.yaml) |
| --- | --- | --- | --- |
| B2_reproducible_env | build_env | devcontainer/compose/nix/Dockerfile | presence |
| B3_dependency_management | build_env | committed lock files | presence |
| B5_composite_check_command | build_env | `check`/`verify`/`ci`/`all` target running lint and test | `check_target_names` |
| C1_formatting | code_quality | formatter config + CI step | presence |
| C2_linting | code_quality | linter config + CI step | presence |
| C4_module_size | code_quality | p90 source-file line count | `file_size_p90_*` |
| D1_readme | documentation | README words + setup/build/test | `readme_min_words` |
| D2_ai_instructions | documentation | AI-instructions file present and detailed | `ai_instructions_min_words` |
| D3_architecture_docs | documentation | ADRs / architecture docs | presence |
| D5_claude_md_size | documentation | instructions-file line count (N/A when none; see D2) | `claude_md_max_lines`, `claude_md_hard_max_lines` |
| D6_layered_context | documentation | non-empty nested CLAUDE.md or `.claude/rules/*.md` | presence |
| V2_precommit_hooks | vcs_safety | pre-commit hook config | presence |
| V3_commit_conventions | vcs_safety | commitlint tooling + enforcement | presence |
| V4_dependency_scanning | vcs_safety | dependabot/renovate/snyk config | presence |

Manual review only (never scored): C3, S3, D4, **D7_reference_implementation**
(is a canonical reference implementation named in CLAUDE.md, and well chosen?).

## Run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/agent-readiness/scanner.py" [REPO_PATH] \
  [--json out.json] [--markdown out.md]
```

- `REPO_PATH` defaults to the current directory.
- With no `--json`/`--markdown`, prints the JSON result and a Markdown summary.
- Weights, tier thresholds, and per-criterion thresholds live in
  `scorecard.yaml` next to the scanner — edit there to tune; no code change.

## Steps

1. Run the scanner against the target repo (default: current repo).
2. Report the tier and overall score, then the per-criterion evidence table.
3. Surface `manual_review_flags` (C3/S3/D4/D7 are heuristic-weak and need human
   judgment) and the list of deferred categories, so the score is not
   mistaken for a full assessment.
4. If asked, suggest the highest-leverage improvements (lowest-scoring MVP
   criteria first).

Do not invent scores — report exactly what the scanner emits, including its
evidence strings.
