---
name: redteam-model
description: Adversarial ML red-team harness against a self-owned model endpoint. 7 probes + report. Rate-limited, budget-bounded, audit-logged.
argument-hint: "<target-url> [--self-certify-owned <path>] [--dry-run] [--agents <id> ...] [--start <id>]"
user-invocable: true
allowed-tools: Read, Write, Bash, Agent
---

# /redteam-model

Orchestrator entry point for the adversarial ML red-team harness. Perform
scope + consent checks, then dispatch the Python orchestrator at
`harness/redteam/orchestrator.py`. Interpret probe artifacts via the four
analyzer agents after the Python passes complete.

Full runtime spec — including bash invocations, exact refusal wording,
flag-interaction matrix, and step output formats — is in
`harness/redteam/ORCHESTRATION.md`. Read it before dispatching.

## Safety constraints (non-negotiable)

1. **Scope-enforced by default.** Targets must resolve to a self-owned
   CIDR (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
   `::1`). Public targets require `--self-certify-owned <path>`.
2. **Self-certification is logged.** Artifact's SHA-256 is written to
   `harness/redteam/results/audit_log.jsonl` with the run timestamp.
3. **Rate-limit + budget enforced.** All HTTP goes through `http_client`
   which enforces `RATE_LIMIT` req/sec and `QUERY_BUDGET` total queries.
   Exhaustion halts the pipeline with `budget_exhausted` status.
4. **Harness-direct invocation blocked.** The `redteam-guard.sh` hook
   refuses direct `python orchestrator.py` calls unless
   `REDTEAM_AUTHORIZED=1` is in env. This command sets it after the
   scope/consent checks pass; scoped to the child process only.

## Parse arguments

Arguments: $ARGUMENTS

**Positional:** `<target-url>` (base URL, no trailing slash).

**Flags:**

- `--self-certify-owned <path>`: authorization artifact for public
  targets. Format: `knowledge/redteam-authorization.md`.
- `--dry-run`: validate config + scope + consent; print step graph; zero
  HTTP requests. Scope enforcement still runs.
- `--agents <id> [<id> ...]`: run only these probe IDs (01-08).
- `--start <id>`: resume from this probe ID (token from prior run's
  `result_store.resume_message()`).

Flag interactions are in `harness/redteam/ORCHESTRATION.md` § "Flag
interactions".

## Procedure

Execute the steps in `harness/redteam/ORCHESTRATION.md`:

1. Resolve and validate scope (Step 1)
2. Validate config (Step 2)
3. Dispatch the Python orchestrator (Step 3)
4. Dispatch analyzer agents (Step 4) — three in parallel, then
   `redteam-report-generator` last
5. Present summary (Step 5)

## Escalation

Stop and ask the user per `harness/redteam/ORCHESTRATION.md` § "Escalation".

## Integration

- Paired with `/security-assessment` for static analysis (independent
  pipelines; can run against the same or different targets).
- Paired with `/export-pdf` for the final report.
- `redteam-guard.sh` PreToolUse hook enforces the authorization gate.
- `knowledge/redteam-authorization.md` declares `--self-certify-owned`
  artifact format.
