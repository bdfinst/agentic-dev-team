# Workflows

This page covers every user-invocable command in the security-assessment plugin. Commands are
sourced from `commands/` — not `skills/`, whose three files are all internal modules with
`user-invocable: false`.

Commands are classified per the top-level/standalone definition:

- **Top-level (multi-agent)** — declares `Agent` in `allowed-tools` and orchestrates multiple
  agents across phases.
- **Standalone (single-purpose)** — no `Agent` tool; single-purpose execution.

---

## Top-Level Commands

### `/security-assessment`

**File:** `commands/security-assessment.md`
**Allowed tools:** Read, Write, Edit, Glob, Grep, Bash, Agent

Full security assessment pipeline — recon, SARIF-first tool detection, judgment review,
FP-reduction, narrative and compliance annotation, service-communication diagram, and executive
report. Works on one repo or multiple repos in parallel; multi-repo runs also produce a cross-repo
summary.

**Phases (per repo):** Phase 0 (RECON) → Phase 1 (static tools) → Phase 1b (five parallel judgment
agents) → Phase 2 (FP-reduction) → Phase 2b (narrative + compliance) → Phase 3 (service-comm diagram)
→ Phase 4 (cross-repo, if multi-target) → Phase 5 (exec report).

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<path> [<path> ...]` | Positional. One or more target repository directories (required). |
| `--start <phase>` | Resume from phase (`0` / `1` / `1b` / `2` / `3` / `4` / `5`). Requires prior phase artifacts in `memory/`. |
| `--agents <phase> [<phase> ...]` | Run only the listed phases. Dependency check is skipped. |
| `--fp-reduce=yes\|no` | Skip Phase 2 FP-reduction when `no`. Default `yes`. |

---

### `/cross-repo-analysis`

**File:** `commands/cross-repo-analysis.md`
**Allowed tools:** Read, Write, Glob, Grep, Bash, Agent

Cross-repo security analysis across two or more target paths. Composes the
`service-comm-parser` and `shared-cred-hash-match` tools with the `cross-repo-synthesizer`
agent to produce a named-attack-chain report. Requires that `/security-assessment` (or
`codebase-recon`) has already run per target — this command does not re-scan.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<path1> <path2> [<path3> ...]` | Positional. Two or more target directories (required). Each must contain a `memory/recon-*.json` artifact. |

---

### `/redteam-model`

**File:** `commands/redteam-model.md`
**Allowed tools:** Read, Write, Bash, Agent

Adversarial ML red-team harness against a self-owned model endpoint. Runs 7 probes, produces a
report, enforces rate limits and budget bounds, and writes an audit log. Accepts only
self-owned targets by default; public hostnames require `--self-certify-owned`.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<target-url>` | Positional. Base URL of the model endpoint (required, no trailing slash). |
| `--self-certify-owned <path>` | Path to an authorization artifact for public targets. Format described in `knowledge/redteam-authorization.md`. |
| `--dry-run` | Validate config, scope, and consent; print step graph without running probes. |
| `--agents <id> ...` | Run only the listed probe IDs. |
| `--start <id>` | Resume from probe `<id>` (requires prior probe artifacts). |

---

## Standalone Commands

### `/export-pdf`

**File:** `commands/export-pdf.md`
**Allowed tools:** Read, Bash

Convert a Markdown report to PDF via pandoc (preferred) or weasyprint (fallback). Skips
gracefully if neither tool is installed.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<report.md>` | Positional. Path to the Markdown report to convert (required). |
| `--output <report.pdf>` | Output path. Defaults to the same base name as the input with a `.pdf` extension. |
| `--css <path>` | Path to a custom CSS stylesheet to apply during conversion. |

---

### `/upgrade`

**File:** `commands/upgrade.md`
**Allowed tools:** Read, Glob, Grep, Bash

Check for and apply security-assessment plugin updates using the official Claude Code plugin
update mechanism. Optionally enables marketplace auto-update.

**Flags:** none. No arguments accepted.

---

## Internal Skills

The three files in `skills/` are internal modules loaded by the commands above; they are not
user-invocable slash commands. See the [skills catalog](../README.md) for their descriptions:

- `skills/security-assessment-pipeline/` — declarative phase graph for `/security-assessment`
- `skills/false-positive-reduction/` — 5-stage FP-reduction rubric
- `skills/compliance-mapping/` — pattern-table compliance mapping with LLM edge annotation
