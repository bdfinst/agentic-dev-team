---
name: competitive-analysis
description: >-
  Compare this plugin against external plugins, tools, feature sets, or ideas to
  find gaps and weaknesses. Produces a structured gap analysis report with rough
  specs for closing each gap. Use this skill whenever the user references
  capabilities from OUTSIDE the plugin — another plugin they found, a competitor's
  tool, a feature list from a different project, a repo URL, or a hypothetical
  concept for capabilities we lack. Trigger phrases include "how do we compare
  to X", "what does Y have that we don't", "what are we missing", "gap analysis",
  "competitive analysis", "weaknesses compared to", "stack up against",
  "where do we fall short", and "should we add X — I saw it in another tool".
  Also trigger when the user pastes a feature list or describes capabilities
  they saw elsewhere and asks whether we should have them. Do NOT trigger for
  internal operations like running reviews, auditing our own agents, adding
  skills, threat modeling, domain analysis, or debugging — those use other skills.
role: orchestrator
user-invocable: true
---

# Competitive Analysis

## Overview

Systematic comparison of the dev-team plugin against another plugin, tool, feature set, or idea. The goal is to surface gaps, weaknesses, and improvement opportunities — then produce rough specs for closing each gap.

This skill is analytical first, generative second. It catalogs what both sides offer, identifies where dev-team falls short, and then drafts actionable specs for each gap. The analysis should be honest — if the other plugin does something better, say so plainly.

## Input Sources

The comparison target can come in several forms. Determine which applies and gather the data accordingly:

| Source | How to gather |
| -------- | -------------- |
| **URL** (repo, docs, marketplace) | Fetch the URL. Look for README, CLAUDE.md, plugin manifests, agent/skill/command directories. If the repo is large, focus on the manifest, README, and directory listing first. |
| **Local path** | Read the directory structure, then key files (README, CLAUDE.md, manifests, agent/skill dirs). |
| **Pasted description or feature list** | Use as-is. Ask clarifying questions only if the description is too vague to compare against. |
| **Concept or idea** | Treat as a hypothetical plugin with the described capabilities. Note in the report that the comparison is against an idea, not a shipped product. |

## Analysis Framework

### Step 1: Catalog dev-team

Read `knowledge/agent-registry.md` for the full inventory. Organize into these capability layers:

- **Team agents** — roles and primary focus areas
- **Review agents** — what code quality aspects are covered
- **Skills** — reusable knowledge modules
- **Commands** — user-invocable workflows
- **Templates** — language/framework-specific scaffolding
- **Knowledge files** — progressive-disclosure reference data
- **Hooks** — automated guards and triggers
- **Workflows** — multi-phase orchestration (Research → Plan → Implement)

### Step 2: Catalog the comparison target

Map the other plugin's capabilities into the same layers where possible. Not every plugin will have all layers — that's fine. For capabilities that don't map cleanly, create an "Other" category and describe them.

For each capability, note:

- What it does (one line)
- How mature it appears (shipped, experimental, documented but not implemented)
- Whether dev-team has an equivalent

### Step 3: Gap analysis

Compare layer by layer. For each gap, classify it:

| Classification | Meaning |
| --------------- | --------- |
| **Missing (dev-team)** | The other plugin has this; we have nothing equivalent |
| **Weaker (dev-team)** | We have something similar, but the other plugin's version is more capable or better designed |
| **Different approach** | Both plugins address this need, but with fundamentally different strategies worth examining |
| **Stronger (dev-team)** | We do this better (include these for balance — the report should be honest in both directions) |

Focus the gap analysis on things that matter. A missing agent for an obscure framework isn't as important as a missing workflow capability. Use judgment about what would actually improve the plugin if addressed.

**Always write the classification with the `(dev-team)` qualifier in every table cell** — never the bare word alone. "Stronger" and "Weaker" are meaningless out of context to a reader scanning a single row without the legend in view; "Missing (dev-team)" and "Stronger (dev-team)" are unambiguous on their own. `Different approach` needs no qualifier since it doesn't imply a direction.

### Step 4: Rough specs for gaps

For each **Missing** or **Weaker** gap, produce a rough spec:

```markdown
### Gap: [Name]

**Classification**: Missing (dev-team) | Weaker (dev-team)
**Layer**: Agent | Skill | Command | Workflow | Hook | Template | Knowledge
**Priority**: High | Medium | Low

**What the other plugin does**:
[1-2 sentences]

**What we have now** (if Weaker):
[What exists and why it falls short]

**Proposed addition**:
- **Type**: [agent / skill / command / hook / template]
- **File**: [proposed file path]
- **Description**: [What it would do — 2-3 sentences]
- **Dependencies**: [What existing components it would interact with]
- **Estimated complexity**: [Small / Medium / Large]
- **Model tier**: [haiku / sonnet / opus — if applicable]
```

For **Different approach** items, don't write a spec — write a short analysis of tradeoffs instead, so the reader can decide whether to adopt the alternative approach.

### Step 5: Prioritization

After listing all gaps, rank the top 5 by impact. Impact considers:

- How many users would benefit
- How fundamental the capability is (workflow > convenience)
- How much effort it would take relative to the value (quick wins first)
- Whether it addresses a real limitation vs. a nice-to-have

## Output Format

Write the report to `reports/competitive-analysis-<date>.md` using this structure.

For the header block and closing Provenance section, follow
`knowledge/report-template.md`; the sections below are this skill's own
body.

(`Date`, `Target`, `Tool versions`, and `Scope` come from that shared
header — `Tool versions` renders `_Not applicable — no tool version applies
to a comparison._` per the empty-section rule; `Source type` has no
shared-contract equivalent and stays as this skill's own field.)

```markdown
# Competitive Analysis: dev-team vs [Target]

**Date**: <date>
**Target**: [Name, URL, or description of what was compared]
**Tool versions**: _Not applicable — no tool version applies to a comparison._
**Scope**: [Layers/capabilities compared]
**Source type**: URL | Local path | Description | Concept

## Executive Summary

[2-3 sentences: what was compared, how many gaps found, top finding]

## Capability Comparison

### [Layer Name]

| Capability | dev-team | [Target] | Classification |
|-----------|-----------------|----------|----------------|
| ...       | ...             | ...      | Missing (dev-team) / Weaker (dev-team) / Different approach / Stronger (dev-team) |

[Repeat for each layer that has differences]

## Gap Specs

[One spec block per Missing or Weaker gap, using the template from Step 4]

## Different Approaches Worth Examining

[Short tradeoff analysis for each Different Approach item]

## Our Strengths

[Brief list of areas where dev-team is stronger — keeps the report balanced]

## Top 5 Priorities

| Rank | Gap | Layer | Complexity | Why |
|------|-----|-------|-----------|-----|
| 1    | ... | ...   | ...       | ... |

## Next Steps

[Concrete recommendations: which gaps to address first, any quick wins, things that need more research]

## Provenance

- Repository: `<repo path>`
- Branch / SHA: `<branch>` / `<sha>`
- Run parameters: `<flags>`
- `dev-team` plugin version: `<plugin_version>`
```

## Presenting Results

After writing the report, display in chat:

1. The file path
2. The executive summary
3. The top 5 priorities table

Do not repeat the full report in chat.
