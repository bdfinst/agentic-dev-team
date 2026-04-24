# Team Organization

This document is a visual index of the agent team. For behavioral details of each agent, see [Agents](agent_info.md). For orchestration mechanics, see [Architecture](agent-architecture.md).

## Team Agents

![Org chart showing the Orchestrator at the top, dispatching to eleven team agents: Software Engineer, QA Engineer, UI/UX Designer, Architect, Product Manager, Technical Writer, Security Engineer, DevOps/SRE Engineer, ADR Author, and Codebase Recon.](diagrams/team-agents.svg)

The Orchestrator sits at the root and routes every request to one or more of the eleven team agents based on task classification. Only the Orchestrator spans phases; the other agents are loaded on demand when their phase begins and unloaded via summarization before the next phase starts. Full roster: [Agents → Team Agents](agent_info.md#team-agents).

## Review Agent Dispatch (Phase 3 Inline Checkpoints)

![Dispatch diagram: a unit of work on the left, a file-type decision layer in the middle, and fan-out to targeted review agents on the right (e.g., JS/TS files → js-fp-review + complexity-review; Svelte → svelte-review; any change → arch-review + doc-review; security surface → security-review).](diagrams/review-dispatch.svg)

The Orchestrator selects review agents based on what changed in each unit of work. Language-agnostic agents (doc-review, arch-review, claude-setup-review, token-efficiency-review) always run; language-specific agents run only when matching file types are present. Full list of review agents and their scopes: [Agents → Review Agents](agent_info.md#review-agents).
