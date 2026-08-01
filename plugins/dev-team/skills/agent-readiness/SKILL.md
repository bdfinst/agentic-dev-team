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

- **Build & Env:** B2 reproducible env, B3 dependency lock files
- **Code Quality:** C1 formatting, C2 linting, C4 module size (p90 line count)
- **Documentation:** D1 README, D2 AI instructions, D3 architecture docs
- **Version Control:** V2 pre-commit hooks, V3 commit conventions, V4 dep scanning

Criteria that need CI-platform data (coverage, flaky rate, durations, branch
policy — T1–T5, B1, B4, C5, S1–S4, V1) and the org-scale Azure DevOps / Jenkins
discovery from the original plan are **deferred** to follow-up phases.
Categories with no MVP criterion (test infrastructure, type safety) are reported
as `deferred` and excluded from the renormalized overall score.

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
3. Surface `manual_review_flags` (C3/S3/D4 are heuristic-weak and need human
   judgment) and the list of deferred categories, so the score is not
   mistaken for a full assessment.
4. If asked, suggest the highest-leverage improvements (lowest-scoring MVP
   criteria first).

Do not invent scores — report exactly what the scanner emits, including its
evidence strings.
