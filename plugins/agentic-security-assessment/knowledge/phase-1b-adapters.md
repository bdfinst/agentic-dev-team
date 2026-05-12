# Phase 1b finding adapters

Loaded by the security-assessment orchestrator at Phase 1b. Defines how
each of the five Phase 1b agents' outputs are appended to the unified
finding stream.

## Two output styles

Five agents run in parallel; they emit in two different shapes that
require different append paths.

### Style 1: adapter required

Agents: `security-review`, `business-logic-domain-review`.

Output is piped through the security-review adapter before appending:

```bash
python3 plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py \
  --input memory/agent-output-<slug>.json \
  --output memory/findings-<slug>.jsonl
```

The adapter is mandatory for these two agents. Non-zero exit halts
Phase 1b with a named error.

### Style 2: direct unified-finding-v1 emission

Agents: `deep-code-reasoning`, `authorization-logic-review`,
`recon-driven-scan`.

These agents emit unified-finding-v1 directly; no adapter is required.
Outputs are appended via jq after all five Phase 1b agents complete:

```bash
jq -c '.[]' memory/deep-reasoning-<slug>.json   >> memory/findings-<slug>.jsonl
jq -c '.[]' memory/authz-review-<slug>.json     >> memory/findings-<slug>.jsonl
jq -c '.[]' memory/recon-driven-<slug>.json     >> memory/findings-<slug>.jsonl
```

Each must validate as a JSON array. Empty `[]` is valid (especially for
`recon-driven-scan` when the RECON narrative is empty/generic — this is
normal, not a failure). A missing file is a Phase 1b failure.

## Failure handling

If any Phase 1b agent fails:

- Log the failure to the audit trail.
- Continue with the remaining agents — Phase 1b is best-effort for
  individual agents.
- If multiple agents fail, surface a coverage warning in the final
  report's Section 6.
