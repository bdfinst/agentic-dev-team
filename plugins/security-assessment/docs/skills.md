# Skills

<!-- GENERATED FILE — do not edit by hand.
     Rows: each plugins/security-assessment/skills/<name>/SKILL.md (and plugins/security-assessment/commands/<name>.md if present).
     Grouping: plugins/security-assessment/skill_categories.yaml (by capability).
     Regenerate: python3 plugins/dev-team/hooks/lib/build_skills_index.py --plugin-dir plugins/security-assessment
     A CI freshness gate (--check) fails if this file drifts from the skills on disk. -->

Skills are the unified reusable capability layer in this plugin. Skills live in `skills/<name>/SKILL.md`; user-invocable commands live in `commands/<name>.md`. This catalog groups them **by capability** (the sections below); each row's description is the file's own frontmatter `description`, verbatim.

Most skills are **user-invocable** as slash commands — shown as `/name`; run them directly or let the Orchestrator dispatch them. The rest are **agent-loaded** knowledge modules — shown as a plain `name` — that agents read for domain expertise.


## Ungrouped

| Skill | Options | File | Description |
| --- | --- | --- | --- |
| compliance-mapping | agent-loaded — not directly invocable | [`compliance-mapping/SKILL.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/skills/compliance-mapping/SKILL.md) | Pattern-table mapping from unified findings to regulatory citations (PCI-DSS, GDPR, HIPAA, SOC2). LLM edge annotator invoked only for llm_review_trigger=true rows. |
| `/cross-repo-analysis` | <path1> <path2> [<path3> ...] | [`commands/cross-repo-analysis.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/commands/cross-repo-analysis.md) | Run cross-repo security analysis across two or more target paths. Composes service-comm-parser + shared-cred-hash-match + cross-repo-synthesizer to produce a named-attack-chain report. |
| `/export-pdf` | <report.md> [--output <report.pdf>] [--css <path>] | [`commands/export-pdf.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/commands/export-pdf.md) | Convert a Markdown report to PDF via pandoc (preferred) or weasyprint (fallback). Skips gracefully if neither is installed. |
| false-positive-reduction | agent-loaded — not directly invocable | [`false-positive-reduction/SKILL.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/skills/false-positive-reduction/SKILL.md) | Hybrid FP-reduction — joern when present, LLM fallback when absent. Six-stage rubric (Stage 0 + Stages 1-5) applied to every finding; emits the disposition register. |
| `/redteam-model` | <target-url> [--self-certify-owned <path>] [--dry-run] [--agents <id> ...] [--start <id>] | [`commands/redteam-model.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/commands/redteam-model.md) | Adversarial ML red-team harness against a self-owned model endpoint. 7 probes + report. Rate-limited, budget-bounded, audit-logged. |
| `/security-assessment` | <path> [<path> ...] [--start <phase>] [--agents <phase> ...] [--fp-reduce=yes\|no] | [`commands/security-assessment.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/commands/security-assessment.md) | Full security assessment pipeline — recon, SARIF-first tool detection, judgment review, FP-reduction, narrative + compliance, service-comm diagram, exec report. Single-repo or multi-repo. |
| security-assessment-pipeline | agent-loaded — not directly invocable | [`security-assessment-pipeline/SKILL.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/skills/security-assessment-pipeline/SKILL.md) | Declarative phase graph for /security-assessment. Phases run in fixed order with dependency enforcement; per-phase artifacts land in memory/ and feed the next phase. |
| `/upgrade` | no flags — run directly | [`commands/upgrade.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/security-assessment/commands/upgrade.md) | Check for and apply security-assessment plugin updates using the official Claude Code plugin update mechanism. |
