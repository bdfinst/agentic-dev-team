# Fixture: aca-scope-overlap

**Skill**: agent-create  
**Scenario**: New agent description overlaps with an existing agent's scope

## Setup

Existing agent `dependency-review` has:
- description: `Detects circular dependencies between modules`
- `## Detect` section: mentions circular imports, dependency cycles, import chains

## Input

- name: `import-cycle-review`
- type: `review`
- description: `Detect circular import dependencies`

## Expected Behavior

Skill emits the exact format:
`Possible overlap with dependency-review: <one-sentence description of shared concept>. Continue anyway? (yes/no)`

Where `<one-sentence description>` describes the shared concept (e.g., "both detect circular dependency patterns").

- On `no`: skill stops, no file written
- On `yes`: skill continues to generation

## Note

This check is advisory. The overlap threshold is ~60% topical similarity. A false positive here causes a UX inconvenience, not a correctness error — the user can always continue.

## Failure Conditions

- Overlap not detected when descriptions clearly overlap → FAIL
- Message format deviates from `Possible overlap with <name>: <sentence>. Continue anyway? (yes/no)` → FAIL
- File written after user answers `no` → FAIL
