# Workflows

The `security-assessment` plugin provides two **orchestrator** commands that sequence multiple phases and agents. They do not implement, review, or merge anything themselves — they delegate each phase to the appropriate agent or skill, hold human gates where required, and surface findings as structured reports.

---

## `/security-assessment`

**File:** [`commands/security-assessment.md`](../commands/security-assessment.md)
**Role:** orchestrator.
**Use when:** running a full security audit against one or more target repos — at a release gate, on a milestone, or before publishing a security report.

### Pipeline phases

| Phase | Runs | Output artifact |
| --- | --- | --- |
| **0. Recon** | `codebase-recon` agent (from `dev-team`) | `memory/recon-<slug>.{json,md}` |
| **1. Tool-first detection** | semgrep, gitleaks, trivy, hadolint, actionlint, custom rulesets | unified findings stream |
| **1b. Judgment** | `security-review`, `business-logic-domain-review` agents | appended findings |
| **1c. Suppression** | `ACCEPTED-RISKS.md` gate (deterministic) | filtered stream + audit log |
| **2. False-positive filter** | `false-positive-reduction` skill (5-stage rubric) | decisions log |
| **2b. Severity floors** | deterministic domain-class calibration | floor-adjusted scores |
| **3. Narrative + compliance** | `tool-finding-narrative-annotator`, `compliance-mapping` skill | 4-domain narrative + compliance JSON |
| **4. Cross-repo** | service-comm parser, shared-cred hash match (multi-target only) | Mermaid diagram + SARIF |
| **5. Exec report** | `exec-report-generator` agent | publication-ready 7-section Markdown |

**Zero-install flow:** `scripts/run-assessment-local.sh` runs the same pipeline from the repo checkout without installing the plugin. See the [User Guide](user-guide-security-assessment.md) for the full runbook.

---

## `/cross-repo-analysis`

**File:** [`commands/cross-repo-analysis.md`](../commands/cross-repo-analysis.md)
**Role:** orchestrator.
**Use when:** analysing shared credentials and service-communication patterns across two or more related repos — microservices suites, platform + tenant repos, monorepo split components.

### Steps

1. Run `codebase-recon` on each target in parallel.
2. Parse inter-service communication shapes (`tools/service-comm-parser.py`).
3. Hash-match credentials across repos (`tools/shared-cred-hash-match.py`).
4. Synthesize named attack chains (`cross-repo-synthesizer` agent).
5. Emit a Mermaid service-comm diagram and a SARIF cross-repo findings file.

---

## `/redteam-model`

**File:** [`commands/redteam-model.md`](../commands/redteam-model.md)
**Role:** adversarial pipeline.
**Use when:** probing a self-owned model endpoint for safety and extraction vulnerabilities. Public targets require a signed `authorization.md` artifact — see [`knowledge/redteam-authorization.md`](../knowledge/redteam-authorization.md).

Eight probes cover: discovery, input evasion, output evasion, system-prompt extraction, data-exfiltration shapes, jailbreak stability, capability disclosure, and report synthesis.

---

## Standalone commands

| Command | Purpose |
| --- | --- |
| `/export-pdf` | Convert a Markdown report to PDF via pandoc / weasyprint |
| `/upgrade` | Update the plugin to the latest marketplace release |

See the [Skills catalog](skills.md) for the full list of skills and commands, and the [Agents page](agent_info.md) for the agents each phase invokes.
