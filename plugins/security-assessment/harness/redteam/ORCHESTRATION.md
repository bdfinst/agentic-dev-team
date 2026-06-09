# Red-Team Orchestration — runtime spec

Operational details for `/redteam-model`. The command reads this on demand
when dispatching the harness.

## Flag interactions

- `--dry-run` + `--start`: dry-run prints the step graph starting at
  `<id>`, does not check the missing-artifact precondition.
- `--dry-run` + `--agents`: dry-run prints only the selected probes.
- `--agents` + `--start`: `--agents` takes precedence (exact probe list).

## Step 1 — Resolve and validate scope

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/harness" python3 -c "
from redteam.lib.scope_check import is_self_owned, refusal_message
import sys
target = sys.argv[1]
accepted, reason = is_self_owned(target)
print('ACCEPTED' if accepted else 'REFUSED')
print(reason)
" "<target-url>"
```

Outcomes:

- **REFUSED + no `--self-certify-owned`**: print refusal message (exact
  wording from `scope_check.refusal_message()`); exit non-zero; no side
  effects.
- **REFUSED + `--self-certify-owned`**: verify artifact exists (`exit
  non-zero with "Self-cert artifact not found: <path>"` if not). Compute
  SHA-256, log to `harness/redteam/results/audit_log.jsonl`:

  ```json
  {"ts": "<iso>", "event": "self_cert", "target": "<url>", "artifact_path": "<path>", "artifact_sha256": "<hex>"}
  ```

  Then proceed.

- **ACCEPTED**: proceed directly (no self-cert needed).

## Step 2 — Validate config

```bash
TARGET_URL=<target-url> PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/harness" python3 -c "from redteam import config; config.validate()"
```

Surface any error (likely: missing `TARGET_URL` or invalid
`RATE_LIMIT` / `QUERY_BUDGET`).

## Step 3 — Dispatch the orchestrator

```bash
REDTEAM_AUTHORIZED=1 \
TARGET_URL=<target-url> \
<other env vars passed through> \
python3 "${CLAUDE_PLUGIN_ROOT}/harness/redteam/orchestrator.py" \
  [--dry-run] \
  [--agents <ids>] \
  [--start <id>]
```

The orchestrator self-bootstraps (it re-execs itself as `redteam.orchestrator`
so its package-relative imports resolve), so it runs directly from any working
directory — no `PYTHONPATH` needed.

**Important**: `REDTEAM_AUTHORIZED=1` is set on THIS invocation only. It
does not persist in the user's shell. The `redteam-guard.sh` PreToolUse
hook allows the orchestrator to run only when this var is set.

Wait for completion. Capture stdout/stderr.

## Step 4 — Dispatch analyzer agents (post-Python)

If `--dry-run` was NOT passed AND the orchestrator produced probe
artifacts (check `harness/redteam/results/`), dispatch the four analyzer
agents in parallel via Agent tool:

| Analyzer | Inputs |
|---|---|
| `redteam-recon-analyzer` | `results/01_recon.json` |
| `redteam-evasion-analyzer` | `results/05_evasion.json`, `results/03_sensitivity.json`, `results/04_boundaries.json` |
| `redteam-extraction-analyzer` | `results/07_extraction.json`, `results/03_sensitivity.json` |
| `redteam-report-generator` | all `results/*.json` + `results/adversarial-report.md` from probe 08 |

`redteam-report-generator` runs LAST — it incorporates the other three's
interpretations. The first three can run in parallel.

## Step 5 — Present summary

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

- Target refuses scope check and `--self-certify-owned` was not passed
  (print refusal; do not prompt for self-cert).
- Self-cert artifact is missing or unreadable.
- `TARGET_URL` is unset in the environment.
- Orchestrator exits with hard error AND no progress-manifest is present
  (no way to resume).
