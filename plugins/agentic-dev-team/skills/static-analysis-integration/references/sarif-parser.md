# SARIF → Unified Finding Parser

Shared normalization layer for every SARIF-emitting tool in the static-analysis pre-pass. Reads a SARIF document, walks `runs[*].results[*]`, and emits unified-finding-v1 objects that validate against `plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json`.

## Field mapping

### Required fields

| Unified finding field | SARIF source | Transform |
|---|---|---|
| `rule_id` | `runs[r].tool.driver.name` + `results[i].ruleId` | Format: `<driver_name_lower>.<ruleId_kebab>`; if `results[i].properties.language` is set, insert it as the middle segment |
| `file` | `results[i].locations[0].physicalLocation.artifactLocation.uri` | Strip `file://` prefix; resolve `uriBaseId` if present; ensure repo-relative POSIX path |
| `line` | `results[i].locations[0].physicalLocation.region.startLine` | Integer, 1-indexed |
| `severity` | `results[i].level` | Map: `error`→`error`, `warning`→`warning`, `note`→`suggestion`, `none` or absent→`info` |
| `message` | `results[i].message.text` | Truncate at 500 chars |
| `metadata.source` | `runs[r].tool.driver.name` | Lowercase; e.g. `"Semgrep"`→`"semgrep"` |
| `metadata.confidence` | `results[i].properties.confidence` | Default: `medium` |

### Optional fields

| Unified finding field | SARIF source | Notes |
|---|---|---|
| `column` | `results[i].locations[0].physicalLocation.region.startColumn` | Omit if absent |
| `end_line` | `results[i].locations[0].physicalLocation.region.endLine` | Omit if absent |
| `end_column` | `results[i].locations[0].physicalLocation.region.endColumn` | Omit if absent |
| `cwe[]` | `runs[r].tool.driver.rules[ruleIndex].properties.cwe` | Wrap as `["CWE-N"]`; accept int or string |
| `cve[]` | `results[i].properties.cve` or rule `properties.cve` | Validate `CVE-YYYY-N` shape |
| `owasp[]` | `runs[r].tool.driver.rules[ruleIndex].properties.owasp` | Passthrough |
| `metadata.source_ref` | `results[i]` (the raw object) | Opaque pointer for debugging only; shape is NOT contract-stable |
| `metadata.exploitability` | `results[i].properties.exploitability` | Map to `demonstrated|plausible|theoretical|unknown`; default `unknown` if absent |

## Rule id prefix conventions

Every unified rule_id follows the schema pattern `^[a-z0-9_-]+(\.[a-z0-9_-]+)+$` — at least two dot-separated segments. The parser applies two rules depending on whether the raw SARIF ruleId is already structured (contains dots).

**Raw ruleId contains dots (semgrep-style):** preserve the structure. Each segment is kebab-cased independently.

```
raw: python.django.audit.sql-injection
out: semgrep.python.django.audit.sql-injection
```

**Raw ruleId is flat:** the parser inserts a capability-tier segment from its tool → tier map.

| Tool driver | Tier segment |
|---|---|
| semgrep | `sast` (rarely used — semgrep rules usually have dots) |
| gitleaks | `secrets` |
| trivy | `iac` for config findings; `cve` for CVE findings; `supply-chain` for vuln findings |
| hadolint | `dockerfile` |
| actionlint | `workflows` |
| entropy-check | `secrets` (custom script — passphrase entropy + cross-env reuse) |
| model-hash-verify | `ml` (custom script — ML model integrity + provenance) |

```
raw: aws-access-key        out: gitleaks.secrets.aws-access-key
raw: DS002                 out: trivy.iac.ds002
raw: CVE-2024-1234         out: trivy.cve.cve-2024-1234
raw: DL3008                out: hadolint.dockerfile.dl3008
raw: shellcheck            out: actionlint.workflows.shellcheck
```

**Kebab-casing rule:** `[^a-z0-9]+` is replaced with a single hyphen, the string is lowercased, and leading/trailing hyphens are stripped.

## Error handling

- A SARIF document missing `runs` or `runs[*].tool.driver.name` is an adapter bug; the parser fails the run with a named-tool error.
- A `result` missing `ruleId` OR `locations` OR `message.text` is discarded with a one-line log entry (`DROPPED: <tool> result missing required SARIF field(s)`). The rest of the run continues.
- A mapped finding that fails unified-finding-v1 schema validation fails the whole run (not silently discarded) — adapter bug.

## Non-goals

- Does not convert SARIF fingerprint / taint-flow data into finding fields. Those remain in `metadata.source_ref` for tools that care.
- Does not enrich findings with exploitability, reachability, or CWE mappings beyond what SARIF carries. Those are downstream concerns (FP-reduction, compliance-mapping).
- Does not canonicalize file paths beyond stripping `file://` and applying `uriBaseId`. Path normalization (symlink resolution, case-folding) is the caller's responsibility.

## Tests

Fixtures under `evals/static-analysis-tools/tier1-mocks/<tool>/` contain a pair of files per tool:

```
<tool>/
  mock.sarif           # raw SARIF output from the tool (captured or synthesized)
  expected-findings.json  # array of unified findings the parser should emit
```

The validator script at `evals/static-analysis-tools/validate.py` iterates every fixture pair, parses `mock.sarif` through the shared parser, and asserts the output equals `expected-findings.json` and validates against the unified-finding-v1 schema.
