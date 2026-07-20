# 3. Document ADR tooling workflow as a skill

Date: 2026-06-01

## Status

Accepted

Documents tooling used by [2. Use sentinel file and argument-shape heuristic for CodeGraph nudge hook](0002-use-sentinel-file-and-argument-shape-heuristic-for-codegraph-nudge-hook.md)

> **Path note (2026-07-20):** the plugin was renamed `agentic-dev-team` → `dev-team` in the bfinster marketplace; substitute `plugins/dev-team/` for `plugins/agentic-dev-team/` to locate the `adr-tools` skill and other files named below. The "31 → 32 skills" count in the Decision section is a point-in-time snapshot, not a current total. This ADR is preserved verbatim as a historical record.

## Context

We started using [npryce/adr-tools](https://github.com/npryce/adr-tools) to manage Architecture Decision Records under `docs/adr/` (project convention; `.adr-dir` at the project root points adr-tools at it). ADR-0002 was the first decision recorded with the tool, and writing it surfaced a non-obvious failure mode: `adr new` opens `$VISUAL`/`$EDITOR` (defaulting to `vi`), which hangs in non-interactive shells — the file is created but empty, and the command exits non-zero. Without documented guidance, every future ADR run will hit the same wall and either:

- Re-discover the workaround (lost time), or
- Skip `adr-tools` entirely and write ADRs by hand (lost link bookkeeping, lost TOC generation, lost supersede semantics — the whole reason to use the tool).

There is already an `adr-author` agent in the plugin, but it covers the *decision framework* and prose authoring, not the CLI mechanics. The two concerns are separable: deciding whether an ADR is warranted vs. driving the tool correctly. Treating them as one would either bloat the agent or leave the mechanics undocumented.

## Decision

Add an `adr-tools` skill (`plugins/agentic-dev-team/skills/adr-tools/SKILL.md`) that documents the CLI mechanics: pre-flight check, the editor caveat with the `EDITOR=true VISUAL=true` workaround, the create / supersede / link / list / generate-toc workflows, and anti-patterns (don't renumber, don't squash decisions, don't write decisions in future tense).

Keep `adr-author` as the decision-framework + prose-authoring agent. The skill delegates to the agent for "should we ADR this?" questions and the agent delegates to the skill for "now run the commands."

Register the skill in `plugins/agentic-dev-team/CLAUDE.md`'s skills count (31 → 32).

## Consequences

**Easier:**

- Any agent or human running `adr new` in a Claude shell gets the editor workaround on first read instead of after losing a turn to the hang.
- The supersede and link mechanics (bidirectional link insertion, automatic Status updates) are documented in one place — agents stop hand-editing Status sections, which keeps the relationship graph consistent.
- `adr generate toc` is named as the required follow-up after every create/supersede, which prevents the index from drifting.

**Harder:**

- Two surfaces to keep aligned (the skill and the `adr-author` agent). Mitigated by an explicit "When to defer to adr-author" section at the bottom of the skill.
- The skill assumes the `docs/adr/` convention (this project's choice) and reads `.adr-dir` for the configured path. Other projects using `doc/adr/` (the adr-tools default) or `docs/adrs/` need to ensure `.adr-dir` matches; the skill's pre-flight calls this out but does not auto-detect.

**Risks:**

- If `adr-tools` ever changes its template path or command surface (last release was v3.0.0), the skill's command examples drift. Mitigated by the skill linking to the upstream README rather than copying it.
