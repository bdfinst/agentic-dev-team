---
name: adr-tools
description: Create and manage Architecture Decision Records using the npryce adr-tools CLI. Use when the user asks to "add an ADR", "record this decision", "create an ADR", "supersede ADR N", "link ADRs", "generate the ADR table of contents", or any request involving the `adr` command. Pairs with the adr-author agent — this skill is the mechanics (commands, files, links); adr-author is the decision framework (when an ADR is warranted) and the prose authoring.
role: worker
user-invocable: true
---

# ADR Tools

Mechanics for working with [npryce/adr-tools](https://github.com/npryce/adr-tools) — the `adr` CLI that creates numbered Architecture Decision Records. Pairs with the [`adr-author`](../../agents/adr-author.md) agent: that agent decides *whether* an ADR is warranted and writes the prose; this skill drives the CLI correctly.

## Pre-flight

```bash
command -v adr || echo "adr-tools not installed — see https://github.com/npryce/adr-tools"
cat .adr-dir 2>/dev/null   # project's configured ADR directory
ls "$(cat .adr-dir 2>/dev/null || echo docs/adr)/" 2>/dev/null | head -3
```

If the pre-flight reports `adr` missing, run `/project-init` to set up this repo's tooling — it installs the `adr` CLI as a capability tool (see its `references/capability-tools.md`) — or install it directly: see [npryce/adr-tools](https://github.com/npryce/adr-tools) (the CLI link is the fallback).

Project convention is `docs/adr/`. `adr-tools` stores the directory in `.adr-dir` at the project root — `adr` reads that file to find the ADRs no matter what subdirectory you're in. If `.adr-dir` is missing, run `adr init docs/adr` once. Do not init silently into a different path — confirm with the user if existing ADRs live somewhere unexpected.

## Editor caveat — the most common failure

`adr new` opens `$VISUAL` or `$EDITOR` (defaulting to `vi`). In a Claude Code shell this hangs the command and exits non-zero — the file is created but empty. Two workarounds:

1. **Preferred — bypass the editor.** Run with a no-op editor, then write the body with the Write tool:

   ```bash
   EDITOR=true VISUAL=true adr new "<title>"
   ```

   The command prints the new file path to stdout. Read it, then replace the template Context/Decision/Consequences sections with the real content via Edit or Write.

2. **Fallback — let it fail, then fill in.** `adr new "<title>"` will create the templated file and exit non-zero from the editor failure. Read the new file (it lives at `<adr-dir>/NNNN-<slugified-title>.md` — typically `docs/adr/`) and fill it in.

The skill always prefers workaround 1.

## Workflows

### Create a new ADR

```bash
EDITOR=true VISUAL=true adr new "<title in plain words>"
```

Then Edit the generated file to fill in:

- **Status** — `Accepted` (default) is fine for decisions already made. Use `Proposed` only if there is genuine open debate.
- **Context** — what forces drove this decision (constraints, alternatives considered, prior art)
- **Decision** — what we are doing (active voice, present tense: "Adopt X" not "We will adopt X")
- **Consequences** — easier / harder / risks. Be specific. If you cannot name a concrete trade-off, the decision probably did not need an ADR.

Commit the new ADR in the same commit (or PR) as the implementation it justifies.

### Supersede an earlier ADR

```bash
EDITOR=true VISUAL=true adr new -s <N> "<new title>"
```

`adr-tools` automatically:

- Inserts a "Supersedes [ADR N](N-old-title.md)" link in the new ADR's Status section.
- Edits ADR N's Status to "Superseded by [ADR M](M-new-title.md)".

Do not delete the old ADR. Its history is the point.

### Link two ADRs without superseding

```bash
adr link <SOURCE> "<LINK>" <TARGET> "<REVERSE-LINK>"
```

Example: `adr link 12 "Amends" 10 "Amended by"`. Use this for relationships like Amends/Refines/Constrains. Multiple links are normal.

### List all ADRs

```bash
adr list
```

Returns sorted file paths. Pipe through `xargs head -1` for a quick title scan.

### Generate the table of contents

```bash
adr generate toc > docs/adr/README.md
```

Run this after creating or superseding any ADR, then commit the regenerated TOC alongside the ADR change. Without this, the index drifts.

### Generate the dependency graph

```bash
adr generate graph | dot -Tpng > docs/adr/graph.png
```

Optional but useful when supersede/link chains get deep. Requires Graphviz (`dot`).

## Anti-patterns to refuse

- **Don't renumber ADRs.** `adr-tools` assigns sequential numbers; references in commits, PRs, and other ADRs depend on them being stable. If a number is wrong, supersede; never renumber.
- **Don't edit ADR status with a text editor when superseding.** Use `adr new -s <N>` so the bidirectional link is automatic and consistent.
- **Don't squash multiple decisions into one ADR.** One decision per file. If a "Decision" section has multiple bullets that are not facets of the same choice, split.
- **Don't write Decision in future tense.** "We will adopt X" reads as a proposal; "Adopt X" reads as a decision. Use the latter for `Accepted` status.
- **Don't omit Consequences.** An ADR without trade-offs is a note, not a decision record. If there genuinely are no consequences, the decision did not need an ADR — defer to the [`adr-author`](../../agents/adr-author.md) decision framework.

## When to defer to adr-author

This skill handles the CLI mechanics. Use the [`adr-author`](../../agents/adr-author.md) agent when:

- It is unclear whether the change *warrants* an ADR (see its decision framework).
- The decision has policy or architectural implications and you want prose with the right scope.
- You need to maintain the ADR index README beyond what `adr generate toc` produces.

A typical flow: the user asks "should we ADR this?" → adr-author decides yes/no and drafts the body → this skill runs the `adr new` / `adr link` commands and regenerates the TOC.
