# security-review-adapter.py — reference

Normalizes the `security-review` agent's JSON output into one
unified-finding envelope v1 JSONL line per issue. Lives in the
static-analysis-integration skill's `adapters/` tree, following the
per-source adapter pattern (actionlint SARIF wrapper, tier-3 bespoke
JSON adapters).

Contract and failure modes are specified in
`plugins/agentic-dev-team/docs/specs/agent-rule-id-adapter.md`. This
reference is the operator-facing summary.

## Prerequisites

- Python 3.10+
- `pip install pyyaml jsonschema`

## CLI

```
python security-review-adapter.py \
  --input agent-output.json \
  --output unified-findings.jsonl \
  [--mapping plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml]
```

Default `--mapping` resolves to the canonical YAML at
`plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml`
(same path `--help` prints).

## Input contract

Agent JSON shape (see `plugins/agentic-dev-team/agents/security-review.md`):

```json
{
  "status": "pass|warn|fail|skip",
  "issues": [
    {
      "category": "A<NN>.<slug>",
      "severity": "error|warning|suggestion",
      "confidence": "high|medium|none",
      "file": "",
      "line": 0,
      "message": "",
      "suggestedFix": ""
    }
  ],
  "summary": ""
}
```

`category` is required on every issue. Format regex:
`^A[0-9]{2}\.[a-z0-9-]+$` (uppercase `A`, two digits, kebab-case slug).

## Output contract

One line per issue. Each line validates against
`plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json`.

```json
{
  "rule_id": "semgrep.generic.sql-injection",
  "file": "api.py",
  "line": 42,
  "severity": "error",
  "message": "...",
  "metadata": {
    "source": "security-review",
    "confidence": "high",
    "source_ref": { "<original agent issue>": "..." }
  }
}
```

- `rule_id` is resolved from the mapping YAML when the category is
  present, otherwise minted as `security-review.<lowercase(category)>`.
- `metadata.source_ref` is the original agent issue, byte-faithful.
- `metadata.source` is always the string `"security-review"`.

## Error semantics

| Condition | Exit | Channel | Message |
|---|---|---|---|
| Malformed category (regex-violating) | 1 | stderr | `ERROR: category '<cat>' does not match required format A<NN>.<slug>` |
| Missing `category` on any issue | 1 | stderr | `ERROR: agent issue missing required 'category' field; upgrade the agent output` |
| Mapping YAML missing / malformed / no `mappings:` key | 1 | stderr | `ERROR: mapping file at <path> is invalid` |
| Emitted finding violates unified-finding-v1 schema | 1 | stderr | `ERROR: emitted finding violates unified-finding-v1 schema (<detail>)` |
| Well-formed-but-unmapped category | 0 | stderr | `WARN: category <CAT> not in mapping at <path>; minted security-review.<lowercase>` |

No partial output: a hard-fail during iteration leaves the output file
truncated to whatever was written before the failing issue.

## Single source of truth

Rule_ids are defined only in the mapping YAML. The adapter source
contains a single rule_id-shaped string literal: the namespace prefix
`"security-review."` used for the fallback path. This invariant is
enforced by an AST walk (see
`evals/security-review-adapter/tests/test_single_source_of_truth_ast.sh`).

## Grep recipe — case translation

The agent emits `category` with an uppercase `A<NN>` prefix (e.g.
`A03.sql-injection`). The adapter lowercases the segment when minting
`security-review.*` rule_ids. Auditors grepping the unified stream
should search for BOTH:

```bash
grep 'security-review\.a03' memory/findings-*.jsonl    # unified-stream side
grep '"category":\s*"A03'  memory/agent-output-*.json  # agent side
```

## Versioning

The mapping YAML has its own `version:` field independent of the
primitives-contract version. Bump the YAML version on any semantic
change (new mapping, rename, removal).
