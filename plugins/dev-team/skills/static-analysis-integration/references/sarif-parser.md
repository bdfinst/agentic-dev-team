# SARIF → Unified Finding Parser

Shared normalization layer for every SARIF-emitting tool in the static-analysis pre-pass. Reads a SARIF document, walks `runs[*].results[*]`, and emits unified-finding-v1 objects that validate against `plugins/dev-team/knowledge/schemas/unified-finding-v1.json`.

## Field mapping

### Required fields

| Unified finding field | SARIF source | Transform |
|---|---|---|
| `rule_id` | `runs[r].tool.driver.name` + `results[i].ruleId` | Format: `<driver_name_kebab>.<middle>.<ruleId_kebab>` — see **Rule id prefix conventions** below for what fills the middle segment |
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

Every unified rule_id follows the schema pattern `^[a-z0-9_-]+(\.[a-z0-9_-]+)+$` — at least two dot-separated segments. The parser applies the rules below depending on the shape of the raw SARIF ruleId.

The middle segment comes from the raw ruleId's own structure, its plugin, or the tool → tier map — **never** from `results[i].properties.language`. An earlier version of the field table above named that property as the source; no implementation ever read it, and the tier map is what every fixture and both consumers actually exercise.

**Raw ruleId contains dots (semgrep-style):** preserve the structure. Each segment is kebab-cased independently.

```
raw: python.django.audit.sql-injection
out: semgrep.python.django.audit.sql-injection
```

**Raw ruleId is `plugin(rule)`-shaped (oxlint):** the plugin becomes the tier segment, so the namespace survives.

```
raw: jsx-a11y(alt-text)        out: oxlint.jsx-a11y.alt-text
raw: eslint(no-magic-numbers)  out: oxlint.eslint.no-magic-numbers
raw: react-perf(jsx-no-new-object-as-prop)
                               out: oxlint.react-perf.jsx-no-new-object-as-prop
```

This branch is checked **before** the dotted and flat cases. Without it the
parentheses are hyphen-flattened by `kebab()` into a single segment
(`oxlint.js.jsx-a11y-alt-text`) — schema-valid, but it erases the boundary
that lets a consumer tell an accessibility finding from a performance one,
which is exactly what #1979's two oxlint concerns need. A malformed shape
(empty half, nested parentheses) falls through to the rules below rather than
producing a partial id.

**Raw ruleId is flat:** the parser inserts a capability-tier segment from its tool → tier map.

| Tool driver | Tier segment |
|---|---|
| semgrep | `sast` (rarely used — semgrep rules usually have dots) |
| gitleaks | `secrets` |
| trivy | `iac` for config findings; `cve` for CVE findings; `supply-chain` for vuln findings |
| hadolint | `dockerfile` |
| actionlint | `workflows` |
| ruff | `python` |
| oxlint | `js` (fallback only — a `plugin(rule)` id uses its plugin instead) |
| entropy-check | `secrets` (custom script — passphrase entropy + cross-env reuse) |
| model-hash-verify | `ml` (custom script — ML model integrity + provenance) |

`ruff` and `oxlint` were absent from this map until #1979, so every finding
from the two language linters was emitted under the `generic` fallback,
contradicting the ids their own entries in `tool-configs.md` advertise.

**Degenerate inputs still produce a valid id.** Two rules keep the output
inside the schema pattern no matter what a driver reports, because a rule id
that fails validation costs the whole finding — file, line, and message
included — even when those are perfectly usable:

- The **driver name is kebab-cased** into the first segment, so a tool
  identifying itself as `Semgrep OSS` yields `semgrep-oss.…` rather than
  embedding a space. A no-op for every tool wired up today.
- A **rule id that kebabs to nothing** (empty string, punctuation only, a
  non-Latin script) becomes the literal segment `unknown` rather than an
  empty trailing segment: `oxlint.js.unknown`, never `oxlint.js.`.

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
