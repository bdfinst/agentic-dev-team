# deep-code-reasoning — rationale and provenance

## Why a surface-scoped freeform agent

Static analysis catches known patterns; this agent catches context-
dependent vulnerabilities that require understanding how components
interact across the codebase — issues that only appear when reading the
code the way a human security researcher would: tracing data flows,
following call chains, and reasoning about authorization design intent
vs. implementation.

## Why scope discipline is mandatory

Unfocused whole-repo reading produces noise; surface-scoped reasoning
produces signal. This agent reads ONLY what RECON identifies as security-
relevant surface — entry points, authentication paths, data-flow
boundaries. If RECON does not identify a surface, fall back to grepping
for common auth patterns rather than reading indiscriminately.

## Why two-location evidence is required

A single suspicious line is a hypothesis, not a finding. Examples of
paired evidence:

- IDOR: `routes/items.py:47` (load by user-supplied id) +
  `services/item_service.py:112` (no ownership check before return)
- TOCTOU: `handlers/payment.py:89` (authorization check) +
  `workers/capture.py:34` (capture without re-verifying authorization)
- Confused deputy: `internal/proxy.py:15` (accepts caller-supplied URL) +
  `config/trust.py:7` (proxy runs with elevated service credentials)

## Why no `low` confidence

A finding you cannot confidently trace is a hypothesis — discard it
rather than push noise downstream for FP-reduction to clean up. The
review pipeline is sensitive to false positives; better to under-emit
than to flood.
