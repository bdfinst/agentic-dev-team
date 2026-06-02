---
name: cross-repo-analysis
description: Run cross-repo security analysis across two or more target paths. Composes service-comm-parser + shared-cred-hash-match + cross-repo-synthesizer to produce a named-attack-chain report.
argument-hint: "<path1> <path2> [<path3> ...]"
user-invocable: true
allowed-tools: Read, Write, Glob, Grep, Bash, Agent
---

# /cross-repo-analysis

You have been invoked with the `/cross-repo-analysis` command.

## Role

Orchestrator for cross-repo security analysis. Composes deterministic tool outputs (service-comm-parser, shared-cred-hash-match) with the `cross-repo-synthesizer` agent's narrative synthesis.

## Constraints

1. **Minimum two target repos.** Below that, this command is a no-op — use `/security-assessment` for a single repo.
2. **No detection.** This command assumes `/security-assessment` has already run per repo (or RECON has been generated per repo). It does not re-scan.
3. **Mermaid passthrough.** The diagram from `service-comm-parser.py` flows through unchanged to the final report.

## Parse arguments

Arguments: $ARGUMENTS

Positional: two or more directory paths. Each must contain `memory/recon-<slug>.json` (produced by an earlier `codebase-recon` run) or the command refuses.

## Steps

### 1. Verify RECON per repo

For each path, locate `memory/recon-*.json`. If any target path lacks a RECON artifact, stop and tell the user: "Target <path> has no RECON artifact — run `codebase-recon` or `/security-assessment <path>` first."

### 2. Run service-comm-parser.py

```bash
python3 plugins/agentic-security-assessment/harness/tools/service-comm-parser.py <path1> <path2> ... > memory/service-comm-<slug>.mermaid
```

Where `<slug>` is a dash-joined concatenation of target repo names.

### 3. Run shared-cred-hash-match.py

```bash
python3 plugins/agentic-security-assessment/harness/tools/shared-cred-hash-match.py <path1> <path2> ... > memory/shared-cred-<slug>.sarif
```

The SARIF output is consumed by the synthesizer agent; it is NOT passed through the unified-finding SARIF parser at this stage (findings are shared-credential hashes, not code-level issues).

### 4. Dispatch cross-repo-synthesizer

Using the Agent tool, dispatch the `cross-repo-synthesizer` agent with inputs:
- List of RECON artifact paths (one per repo)
- Path to the Mermaid file from step 2
- Path to the shared-cred SARIF from step 3

The agent produces `memory/cross-repo-analysis-<slug>.md`. Wait for completion.

### 5. Present summary

Print to stdout:
```
Cross-repo analysis complete.

  Target repos: <list>
  Mermaid diagram: memory/service-comm-<slug>.mermaid
  Shared credentials: memory/shared-cred-<slug>.sarif (<N> groups, <M> total occurrences)
  Named attack chains: <count from the synthesizer output>
  Full report: memory/cross-repo-analysis-<slug>.md
```

## Integration

- Typically run after `/security-assessment` has completed per repo (so disposition registers exist).
- The exec-report-generator reads `memory/cross-repo-analysis-<slug>.md` when producing the cross-repo summary report (one of the four reference outputs).

## Escalation

Stop and ask the user when:
- Only one target path is passed (requires at least two).
- Any target path lacks a RECON artifact.
- `service-comm-parser.py` or `shared-cred-hash-match.py` fails with a non-zero exit code — surface the error; do not silently swallow.
