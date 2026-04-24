---
name: redteam-model
description: Adversarial ML red-team harness against a self-owned model endpoint. Runs 7 probes (recon, schema discovery, feature sensitivity, boundary mapping, evasion, input validation, extraction) + report generation. Rate-limited, budget-bounded, audit-logged.
argument-hint: "<target-url> [--self-certify-owned <path>] [--dry-run] [--agents <id> ...] [--start <id>]"
user-invocable: true
allowed-tools: Read, Write, Bash, Agent
---

# /redteam-model

You have been invoked with the `/redteam-model` command.

## Role

Orchestrator entry point for the adversarial ML red-team harness. Performs scope + consent checks, then dispatches the Python orchestrator at `plugins/agentic-security-assessment/harness/redteam/orchestrator.py`. Interprets probe artifacts via the four analyzer agents after the Python passes complete.

## Safety constraints (non-negotiable)

1. **Scope-enforced by default.** Targets must resolve to a self-owned CIDR (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1`). Public targets require `--self-certify-owned <path>`.
2. **Self-certification is logged.** The artifact file's SHA-256 is written to the audit log (`harness/redteam/results/audit_log.jsonl`) with the run timestamp.
3. **Rate-limit + budget enforced.** All HTTP goes through `http_client` which enforces `RATE_LIMIT` req/sec and `QUERY_BUDGET` total queries. Exhaustion halts the pipeline with `budget_exhausted` status.
4. **Harness-direct invocation blocked.** The `redteam-guard.sh` hook refuses any direct `python orchestrator.py` call unless `REDTEAM_AUTHORIZED=1` is in the environment. This command sets it after the scope / consent checks pass; the variable is scoped to the child process only.

## Parse arguments

Arguments: $ARGUMENTS

**Positional:** `<target-url>` (the base URL of the model service, no trailing slash).

**Flags:**
- `--self-certify-owned <path>`: path to an authorization artifact declaring the operator owns the target. Required for public targets. See `knowledge/redteam-authorization.md` for the expected format.
- `--dry-run`: validate config, scope, and consent; print the step graph from whatever --start indicates (or probe 01 by default); make zero HTTP requests. Scope enforcement still runs.
- `--agents <id> [<id> ...]`: run only these probe IDs (01-08).
- `--start <id>`: resume from this probe ID. The token is exactly what `result_store.resume_message()` prints after a prior mid-run failure.

Flag-interaction matrix:
- `--dry-run` + `--start`: dry-run prints the step graph starting at `<id>`, does not check the missing-artifact precondition.
- `--dry-run` + `--agents`: dry-run prints only the selected probes.
- `--agents` + `--start`: `--agents` takes precedence (exact probe list).

## Steps

### 1. Resolve + validate scope

```bash
python3 -c "
from plugins.agentic_security_review.harness.redteam.lib.scope_check import is_self_owned, refusal_message
import sys
target = sys.argv[1]
accepted, reason = is_self_owned(target)
print('ACCEPTED' if accepted else 'REFUSED')
print(reason)
" "<target-url>"
```

If REFUSED and `--self-certify-owned` was NOT passed:
- Print the refusal message (exact wording from `scope_check.refusal_message()`)
- Exit non-zero with no side effects

If REFUSED and `--self-certify-owned` was passed:
- Verify the artifact exists. If not, print `Self-cert artifact not found: <path>` and exit non-zero.
- Compute SHA-256 of the artifact. Log to `harness/redteam/results/audit_log.jsonl`:
  ```
  {"ts": <iso>, "event": "self_cert", "target": "<url>", "artifact_path": "<path>", "artifact_sha256": "<hex>"}
  ```
- Proceed.

If ACCEPTED, proceed directly (no self-cert needed).

### 2. Validate config

```bash
TARGET_URL=<target-url> python3 -c "from plugins.agentic_security_review.harness.redteam import config; config.validate()"
```

If this errors, surface the message (likely: missing `TARGET_URL` or invalid `RATE_LIMIT`/`QUERY_BUDGET`).

### 3. Dispatch orchestrator

Build the command line:

```bash
REDTEAM_AUTHORIZED=1 \
TARGET_URL=<target-url> \
<other env vars passed through> \
python3 -m plugins.agentic_security_review.harness.redteam.orchestrator \
  [--dry-run] \
  [--agents <ids>] \
  [--start <id>]
```

**Important**: `REDTEAM_AUTHORIZED=1` is set on THIS invocation only. It does not persist in the user's shell. The `redteam-guard.sh` PreToolUse hook in this plugin's `settings.json` allows the orchestrator to run only when this var is set.

Wait for the orchestrator to complete. Capture stdout/stderr.

### 4. Dispatch analyzer agents (post-Python)

If `--dry-run` was NOT passed AND the orchestrator produced probe artifacts (check `harness/redteam/results/`), dispatch the four analyzer agents in parallel via Agent tool:

| Analyzer | Inputs |
|---|---|
| `redteam-recon-analyzer` | `results/01_recon.json` |
| `redteam-evasion-analyzer` | `results/05_evasion.json`, `results/03_sensitivity.json`, `results/04_boundaries.json` |
| `redteam-extraction-analyzer` | `results/07_extraction.json`, `results/03_sensitivity.json` |
| `redteam-report-generator` | all `results/*.json` + `results/adversarial-report.md` from probe 08 |

The report generator must run last (it incorporates the other three's interpretations). The first three can run in parallel.

### 5. Present summary

Print:

```
Red-team assessment complete.

  Target: <target-url>
  Scope: <self-owned | self-cert: <sha256 first 12>>
  Probes run: <list from orchestrator summary>
  Budget: <N used> / <QUERY_BUDGET>
  Artifacts: harness/redteam/results/
  Report: harness/redteam/results/adversarial-report.md
        (or resume-token from the summary if the run halted mid-way)

  Run `/export-pdf adversarial-report.md` to produce a PDF.
```

## Escalation

Stop and ask the user when:
- Target refuses scope check and `--self-certify-owned` was not passed (print the refusal message; do not prompt for self-cert).
- Self-cert artifact is missing or unreadable.
- `TARGET_URL` is unset in the environment.
- Orchestrator exits with hard error AND no progress-manifest is present (no way to resume).

## Integration

- Paired with `/security-assessment` for static analysis (independent pipelines; the two can run against the same or different targets).
- Paired with `/export-pdf` for the final report.
- `redteam-guard.sh` PreToolUse hook in this plugin's settings.json enforces the authorization gate.
- `knowledge/redteam-authorization.md` declares the expected format of the `--self-certify-owned` artifact.
