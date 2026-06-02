# 5. On-demand knowledge indexing with four freshness gates

Date: 2026-06-02

## Status

Accepted

## Context

Agents in this plugin reference markdown files under `knowledge/` and skill
bodies under `skills/<name>/SKILL.md`. Before this change, every agent that
needed one section of a knowledge file had to read the file end-to-end —
`owasp-detection.md` is ~130 lines, `security-primitives-contract.md` is
~295. Agents paid for the whole file even when they only needed one of its
H2 sections, inflating sub-agent context for every dispatch that consults
the corpus. Discovery was also weak: an agent that wanted "the OWASP A03
detection patterns" had no way to find that section short of reading the
file in full.

Three design questions shaped this ADR.

### Q1. Indexing technology

The corpus is small (≈50 files, ≈4,600 lines, ≈300 H2/H3 sections), the
access pattern is exact-match lookup ("the OWASP A03 rule"), and update
cadence is `git commit`-bound rather than streaming. Three options were
considered:

- **CodeGraph (the project's existing SQLite knowledge graph).** Rejected:
  CodeGraph indexes code symbols (functions, classes, edges), not prose
  sections. Treating markdown sections as "symbols" would require schema
  extensions in an upstream dependency and confuse the existing graph's
  semantics.
- **Embedding-based retrieval.** Rejected: the corpus is too small to
  justify a vector store. The access pattern is "give me the OWASP A03
  rule," not "find me semantically related content."
- **Static JSON index, checked in.** Selected. A single
  `knowledge/index.json` file mapping each corpus path to its H2/H3
  sections, with one-sentence summaries plus slugified GitHub-style
  anchors. Loaded with a single `jq` (or any JSON reader) lookup; agents
  then `Read` the source file with `offset`/`limit` for the matching
  section.

### Q2. How to keep the index fresh as the corpus evolves

A checked-in index is only useful if it stays current. Four enforcement
layers were considered, with overlapping coverage:

1. **PostToolUse hook** on `Edit|Write`. Regenerates the index whenever an
   Edit or Write touches a corpus file. Fail-open so a buggy hook can never
   block an edit.
2. **Pre-commit sibling hook** on `PreToolUse:Bash`. Inspects staged corpus
   files; runs the builder in `--check` mode against the working tree; on
   drift, exits 2 with a two-line remediation (rebuild + `git add`).
3. **CI bats freshness gate**. One assertion in
   `tests/repo/knowledge_index_current.bats` that the on-disk index matches
   a fresh build. Catches anything that slips past the two runtime hooks.
4. **Anchor-citation gate**. `tests/agents/agent_knowledge_anchor_tests.bats`
   enforces that every reference to `knowledge/X.md` or `skills/Y/SKILL.md`
   in agent prose either cites a section anchor present in the index OR
   carries a literal `Whole-file load:` rationale. This catches a different
   class of drift — agents pointing at sections that no longer exist.

All four were adopted. Each layer is cheap to implement; the redundancy
matches the contributor's flow (auto-fix on edit, hard block on commit,
strict gate in CI, per-reference correctness over time) without fighting
it.

### Q3. Builder implementation

The first builder was bash + jq + awk + per-section python — one shell
script driving ~300 `jq` invocations per build (one per section across 50
files). Runtime was ~25 seconds per build, which made the PostToolUse hook
visibly slow on save.

The builder was rewritten as a single Python process
(`build_knowledge_index.py`), with a thin shell wrapper (`build-knowledge-
index.sh`) that `exec`s it so existing callers keep their stable entry
point. The new builder runs in ~45ms for the real corpus — a 550× speedup
— with byte-identical output (verified via `cmp` against the pre-rewrite
file).

## Decision

1. **Ship a static, checked-in `knowledge/index.json`.** Single source of
   truth keyed by repo-relative file path, then by H2/H3 section header,
   with each entry holding exactly `summary` (one sentence) and `anchor`
   (slugified GitHub style). No timestamps; rebuilds with unchanged inputs
   are byte-identical.

2. **Four freshness gates**, defense-in-depth:
   - PostToolUse `Edit|Write` hook auto-regenerates on save
   - PreToolUse `Bash` sibling hook blocks `git commit` on stale index
   - CI bats test asserts the on-disk index is current
   - Anchor-citation bats test asserts every agent reference resolves

3. **Single-process Python builder.** The shell file remains as a thin
   `exec python3 …` wrapper. No new dependency: Python 3 is already a hard
   dep via `/init-dev-team`. The previous bash+jq+awk pipeline was
   rewritten in place; jq is no longer required by the builder.

4. **Anchor-citation discipline for agent prose.** Every reference in an
   agent file uses either `knowledge/X.md#anchor` or the literal token
   `Whole-file load:` in the same paragraph. The bats gate enforces this
   going forward. Cross-plugin references (e.g.
   `plugins/agentic-security-assessment/skills/…`) are explicitly excluded
   from the gate's scope.

## Consequences

**Positive.**

- Sub-agents reading knowledge files now consult one JSON file and then
  `Read` only the matching section. Token cost per dispatch drops
  proportionally to the file's section count.
- Discovery is mechanical: any agent (or human) can grep the index for
  "OWASP" and get a direct anchor link rather than a file path.
- Drift is caught at four different points in the contributor's flow.
- The Python rewrite reduced per-save latency from ~25s to ~45ms, making
  the PostToolUse hook effectively invisible to the user.
- The shell wrapper keeps the old entry point stable, so the PostToolUse
  hook, pre-commit sibling, `/model-routing-check`-style commands, and any
  manual invocations keep working unchanged across the rewrite.

**Negative.**

- The index is checked into git, so any corpus edit produces a parallel
  diff in `knowledge/index.json`. The diff is meaningful (no timestamps
  or build IDs), but reviewers see twice as much in the PR.
- The `Whole-file load:` escape hatch is a stringly-typed contract — a
  typo (`Whole file load:` without the hyphen) fails the gate with a
  message that quotes the required token, but the contributor still
  needs to know the convention exists.
- Cross-plugin references are skipped by the anchor gate. A reference to
  `plugins/agentic-security-assessment/skills/foo/SKILL.md` is never
  validated — if that file moves or its sections rename, the agent
  reference goes stale silently.

**Out of scope (recorded as future work).**

- Indexing `docs/**.md` (project documentation; overlaps with CLAUDE.md's
  catalog role).
- Fuzzy keyword search across summaries (premature; corpus is small enough
  that exact-match works).
- Embedding-based retrieval (same).
- Cross-plugin reference validation (the anchor gate would need to load
  the *other* plugin's index, which doesn't currently exist).

## Implementation summary

> **Path note (2026-06-02):** the plugin was renamed `agentic-dev-team` → `dev-team` in the bfinster marketplace. Paths below reflect the pre-rename layout; substitute `plugins/dev-team/` for `plugins/agentic-dev-team/` to locate current files. This ADR is preserved verbatim as a historical record.

| Layer | File |
|---|---|
| Index data | `plugins/agentic-dev-team/knowledge/index.json` |
| Builder | `plugins/agentic-dev-team/hooks/lib/build_knowledge_index.py` |
| Builder wrapper | `plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh` |
| Shared corpus regex | `plugins/agentic-dev-team/hooks/lib/knowledge-index-paths.sh` |
| Shared commit detection | `plugins/agentic-dev-team/hooks/lib/pre-commit-detect.sh` |
| PostToolUse hook | `plugins/agentic-dev-team/hooks/knowledge-index.sh` |
| Pre-commit sibling | `plugins/agentic-dev-team/hooks/pre-commit-knowledge-index.sh` |
| Consumer pattern docs | `plugins/agentic-dev-team/agents/orchestrator.md` (Knowledge index — consumer usage pattern) and `plugins/agentic-dev-team/docs/agent-architecture.md` (Knowledge Index) |
| Tests | `tests/hooks/knowledge_index_*.bats`, `tests/repo/knowledge_index_*.bats`, `tests/agents/agent_knowledge_anchor_tests.bats` |

See: `agents/orchestrator.md` → Knowledge index — consumer usage pattern
for the canonical lookup flow; `bash plugins/agentic-dev-team/hooks/lib/
build-knowledge-index.sh --check` for ad-hoc verification.
