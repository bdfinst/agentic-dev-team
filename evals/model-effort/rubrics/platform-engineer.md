# Rubric: platform-engineer

A good answer leads with operational impact and the rollback path, reasons in failure modes and blast radius, and prefers observable, reversible, incremental changes. It grounds every recommendation in the provided pipeline, config, and incident material and ends with how to verify the deployment is healthy.

## Criteria

- **leads-with-impact-and-rollback**: The answer opens with the operational impact or rollback path, not with preamble.
- **grounded-in-fixture**: Each problem the answer names points to a specific file, line, or fact in the provided material; no invented infrastructure.
- **reversible-incremental**: The recommendations favor gradual, observable, reversible rollout over big-bang change.
- **health-verification**: The answer says how to verify the deployment or change is healthy (the signals or checks to watch).
