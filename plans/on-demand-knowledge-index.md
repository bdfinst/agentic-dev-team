# Plan: On-Demand Knowledge Index

**Created**: 2026-06-01
**Branch**: cut `feat/knowledge-index` from `main` before Step 0
**Status**: implemented
**Spec**: [docs/specs/on-demand-knowledge-index.md](../docs/specs/on-demand-knowledge-index.md)

## Goal

Ship a deterministic, checked-in `knowledge/index.json` that catalogs
every H2/H3 section across `knowledge/**.md` and `skills/**/SKILL.md`
with a one-sentence summary plus a slugified anchor. Wire three
defense-in-depth freshness gates: a PostToolUse hook that regenerates
on save (auto-fix), a pre-commit check that blocks stale commits
(safety net), and a CI bats test that catches drift on PRs (strict
gate). Migrate every existing agent reference to cite a section anchor
so agents read only the section they need.

## Acceptance Criteria

Mirrors the spec's AC table. Each TDD step traces back to specific AC IDs.

- [ ] **AC1** Index file exists and parses as JSON
- [ ] **AC2** Minimal entry shape (`summary` + `anchor` only)
- [ ] **AC3** Determinism (byte-identical on rebuild)
- [ ] **AC4** No timestamps in index
- [ ] **AC5** Sort order (files lex; sections source-position)
- [ ] **AC6** Corpus coverage (both trees; nothing outside)
- [ ] **AC7** Summary shape (single sentence, ≥8 chars, ends in `.`)
- [ ] **AC8** Anchor shape (GitHub slug regex)
- [ ] **AC9** Anchor uniqueness within a file
- [ ] **AC10** PostToolUse rebuilds on corpus edit
- [ ] **AC11** PostToolUse ignores unrelated edits
- [ ] **AC12** PostToolUse fail-open posture
- [ ] **AC13** Pre-commit blocks on stale
- [ ] **AC14** Pre-commit passes when current
- [ ] **AC15** Pre-commit skips when irrelevant
- [ ] **AC16** CI freshness gate
- [ ] **AC17** `--check` mode is read-only
- [ ] **AC18** `--check` diff output on drift
- [ ] **AC19** Agent references cite anchors (or `Whole-file load:`)
- [ ] **AC20** Index is git-tracked (not gitignored)
- [ ] **AC21** No extra build artifacts after rebuild
- [ ] **AC22** Settings registration of the PostToolUse hook
- [ ] **AC7a** Sentence-boundary correctness (parameterised abbrev/initial/truncation cases)
- [ ] **AC9a** Within-file slug disambiguation (`overview` + `overview-1`)
- [ ] **AC13a** Pre-commit catches working-tree drift past staged pair
- [ ] **AC17a** `--check` clean run is silent (zero stdout/stderr)
- [ ] **AC23** Builder performance (opt-in gate, < 10s for 10 rebuilds)
- [ ] **AC24** jq version floor (`jq >= 1.6` enforced + documented)

## User-Facing Behavior

Gherkin scenarios are the single source of truth — copied verbatim from
the spec. See `docs/specs/on-demand-knowledge-index.md` §User-Facing
Behavior. Each scenario maps to one or more steps below via the `Maps to`
line.

## Implementation Strategy

Four layers, each independently testable:

1. **Builder** (`hooks/lib/build-knowledge-index.sh`) — pure bash + jq.
   Two modes: default rewrites `knowledge/index.json`; `--check` diffs
   against the on-disk file in a tempdir and exits non-zero on drift.
   Determinism is enforced by sorted output, source-position section
   ordering, and the absence of any timestamp field.
2. **PostToolUse hook** (`hooks/knowledge-index.sh`) — thin adapter on
   the `Edit|Write` matcher. Pattern-matches `tool_input.file_path`
   against the corpus, shells out to the builder, fail-open on any
   error.
3. **Pre-commit gate** — a NEW sibling hook
   `hooks/pre-commit-knowledge-index.sh` registered alongside
   `pre-commit-review.sh` under `PreToolUse:Bash`. The two hooks share a
   common `git commit` detection helper (`hooks/lib/pre-commit-detect.sh`)
   but otherwise have independent concerns. The sibling invokes the
   builder in `--check` mode and `exit 2`s with a two-line remediation
   (regen command + `git add`) on drift.
4. **CI bats test** (`tests/repo/knowledge_index_current.bats`) — one
   assertion: `--check` exits 0 on a clean tree. Runs in the standard
   `bats tests/ -r` invocation and gates `/pr`.

Agent integration follows the gate work, not preceding it: once the
index is correct and the bats anchor-citation test runs, we sweep every
agent reference that needs an anchor. Sweep is mechanical but
non-trivial (73 references across the agent corpus).

Bats infrastructure follows established patterns: `tests/hooks/` for
hook + builder tests; `tests/repo/` for the freshness gate;
`tests/agents/` for the anchor-citation rule. The `tests/hooks/fake-bin`
PATH-override pattern is used for any test shimming.

## Steps

### Step 0: Shared corpus-path helper

**Complexity**: trivial
**Maps to**: precondition for Steps 1, 7, 9, 11 (all reference the same corpus regex)
**Why this step**: the pre-commit hook, PostToolUse hook, and anchor-citation test all need to ask "is this path part of the indexed corpus?". Lifting the regex into one helper now prevents a 3-file edit when scope changes later (design reviewer's missing-abstraction concern).
**RED**: `tests/hooks/knowledge_index_paths_tests.bats`:

- Sourcing `hooks/lib/knowledge-index-paths.sh` exposes `_is_corpus_path` (a bash function) and `CORPUS_REGEX` (an exported variable).
- `_is_corpus_path plugins/agentic-dev-team/knowledge/owasp-detection.md` returns 0.
- `_is_corpus_path plugins/agentic-dev-team/skills/specs/SKILL.md` returns 0.
- `_is_corpus_path plugins/agentic-dev-team/knowledge/schemas/foo.json` returns 1.
- `_is_corpus_path plugins/agentic-dev-team/agents/security-review.md` returns 1.
- `_is_corpus_path plugins/agentic-dev-team/commands/code-review.md` returns 1.
- `CORPUS_REGEX` is non-empty and the same regex `_is_corpus_path` uses.

**GREEN**: Create `plugins/agentic-dev-team/hooks/lib/knowledge-index-paths.sh`. One regex constant; one function. Header comment explains the single-source-of-truth role.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/lib/knowledge-index-paths.sh`, `tests/hooks/knowledge_index_paths_tests.bats`
**Commit**: `feat(knowledge-index): shared corpus-path helper`

### Step 1: Builder — happy path on a tiny fixture corpus

**Complexity**: standard
**Maps to**: AC1, AC2, AC7 (preconditions for AC7a)
**RED**: `tests/hooks/knowledge_index_builder_tests.bats`:

- A temp corpus (`$BATS_TMPDIR/knowledge/foo.md` with H2 "Bar" and a one-line body, plus `$BATS_TMPDIR/skills/baz/SKILL.md` with H2 "Qux") is built into a temp index path via env-var overrides.
- The output is valid JSON (`jq -e .`).
- Top-level keys are exactly the two source paths, repo-relative.
- The `foo.md → Bar` entry has exactly two fields `summary` and `anchor`; no other keys.
- `summary` length ≥ 8.
- `anchor` matches `^[a-z0-9][a-z0-9-]*[a-z0-9]$` and equals `bar`.

Builder paths are injected via env vars (`KNOWLEDGE_INDEX_CORPUS_ROOTS`, `KNOWLEDGE_INDEX_OUTPUT`) — **TEST-ONLY injection seams**, documented as such in the header comment per the `model-resolve.sh` precedent. Production callers never set these.

**GREEN**: Create `plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh`. Pure bash + jq walk over the two corpora; emit a single `jq -n` invocation building the nested object. Header comment block documents the env vars as test-only and the `jq >= 1.6` requirement (enforced in Step 9.5).
**REFACTOR**: Extract `_extract_sections` (markdown → section list) and `_emit_index` (section list → JSON).
**Files**: `plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh`, `tests/hooks/knowledge_index_builder_tests.bats`
**Commit**: `feat(knowledge-index): builder happy path with minimal entry shape`

### Step 2: Builder — H2 + H3 coverage with source-position ordering

**Complexity**: standard
**Maps to**: AC5 (per-file ordering), AC8 (anchor shape for both H2 and H3), AC9 + AC9a (within-file uniqueness including duplicate headers)
**RED**: Extend bats with:

- A fixture file containing H2/H3 nesting in deliberately non-alphabetical order (e.g., `## Zebra`, `### Sub`, `## Alpha`). Output's section keys appear in source order: `Zebra`, `Sub`, `Alpha`. H1 absent. H4 absent.
- Both H2 and H3 anchors match `^[a-z0-9][a-z0-9-]*[a-z0-9]$` (catches a slug bug that strips only `##` and leaves `#` on H3).
- A fixture with two identically-named sections (`## Overview` appearing twice) produces anchors `overview` and `overview-1` (GitHub disambiguation suffix); no two sections in the same file share an anchor.

**GREEN**: Extend `_extract_sections` to walk `##` and `###` only, preserving file order. Add per-file slug disambiguation counter.
**REFACTOR**: Pull the regex/awk extraction into a single subshell pipeline; comment why H1/H4 are excluded.
**Files**: same as Step 1.
**Commit**: `feat(knowledge-index): H2/H3 coverage with source-order section keys and slug disambiguation`

### Step 3: Builder — determinism + lexicographic file ordering

**Complexity**: standard
**Maps to**: AC3, AC4, AC5 (file ordering)
**RED**: Three bats cases:

- Two consecutive rebuilds of the same corpus produce byte-identical output (`cmp`).
- Top-level keys appear in lexicographic order regardless of filesystem walk order (test by creating fixture files with names that hash out of order: `zoo.md`, `alpha.md`, `mid.md`).
- The output contains no field named `generated_at`, `timestamp`, `build_id`, `updated`, or any ISO-8601-shaped string.

**GREEN**: Sort the file list before iterating. Use `jq -nc --slurpfile entries ...` or equivalent to ensure the final object's key order is deterministic. Strip any incidental jq output non-determinism.
**REFACTOR**: One-line shell guard `LC_ALL=C` to lock sort behavior.
**Files**: same as Step 1.
**Commit**: `feat(knowledge-index): deterministic builder output (sort + no timestamps)`

### Step 4: Builder — summary extraction with operational sentence-boundary rule

**Complexity**: standard
**Maps to**: AC7, AC7a
**RED**: Two test groups.

**Group A — body-source precedence**:

- Section body starts with a code fence → summary is the first non-code, non-blank line.
- Section body is only a bullet list → summary is the first bullet's text (with leading `-` stripped) followed by a period if absent.
- Section body is empty until the next sub-header → summary is the first sentence of the first child section.
- Section body has a sentence spanning multiple wrapped lines → summary captures the full sentence up to the boundary.

**Group B — `_first_sentence` boundary rule (AC7a, parameterised)**:

| Input | Expected summary |
|---|---|
| `Detection patterns for SQL, NoSQL, and ORM injection vectors.` | `Detection patterns for SQL, NoSQL, and ORM injection vectors.` |
| `Frameworks like e.g. Django need careful handling. More follows.` | `Frameworks like e.g. Django need careful handling.` |
| `Authored by J. Doe and others. Reviewed by team.` | `Authored by J. Doe and others.` |
| `Use Mr. Smith's heuristic. Then iterate.` | `Use Mr. Smith's heuristic.` |
| `Validation, vs. trust assumptions. Always validate.` | `Validation, vs. trust assumptions.` |
| (260-char paragraph with no terminator) | First 240 chars truncated at last whitespace + `…` |

**GREEN**: Implement the precedence rules and the deterministic sentence-boundary algorithm from the spec's §Builder section.
**REFACTOR**: Extract `_first_sentence` helper; abbreviation token list in a constant.
**Files**: same as Step 1.
**Commit**: `feat(knowledge-index): summary extraction across code, list, and empty bodies`

### Step 5: Builder — `--check` mode

**Complexity**: standard
**Maps to**: AC17, AC17a, AC18
**RED**: Bats:

- With on-disk index matching what a rebuild would produce, `--check` exits 0 AND produces zero bytes on stdout AND zero bytes on stderr (AC17a: silence is part of the contract).
- With on-disk index forcibly out of date (one section renamed in source but not in the index), `--check` exits non-zero; stderr contains `---` / `+++` / `@@` unified-diff markers.
- `--check` does not modify any file under the corpus or output paths (verified via `find ... | sort | shasum -a 256` before/after).

**GREEN**: Build to a tempfile under `mktemp -d`; `diff -u` against the on-disk file; pass stderr through. Status code reflects the diff.
**REFACTOR**: Centralize tempdir cleanup in a `trap`.
**Files**: same as Step 1.
**Commit**: `feat(knowledge-index): --check mode for freshness gates`

### Step 6: Build the real index, check it in (with gitignore gate)

**Complexity**: standard
**Maps to**: AC1, AC6, AC20
**Bump rationale (from acceptance reviewer)**: this is the first integration of the builder against the real corpus. Unusual encodings, SKILL.md files with no H2 headers, or `knowledge/schemas/` exclusion bugs surface here. Budget time for corpus-specific edge cases.
**RED**: Two new bats files under `tests/repo/` (single test-tree location):

- `tests/repo/knowledge_index_shape.bats`:
  - `plugins/agentic-dev-team/knowledge/index.json` exists and parses (`jq -e .`).
  - Every `plugins/agentic-dev-team/knowledge/*.md` except `knowledge/schemas/` appears as a top-level key.
  - Every `plugins/agentic-dev-team/skills/*/SKILL.md` appears as a top-level key.
  - No file outside those two trees appears (no `docs/`, no `agents/`, no `commands/`).
- `tests/repo/knowledge_index_gitignore.bats` (AC20):
  - `git ls-files plugins/agentic-dev-team/knowledge/index.json` returns the path with exit 0.
  - `git check-ignore plugins/agentic-dev-team/knowledge/index.json` exits non-zero.

**GREEN**: Run the builder against the real corpus; commit `knowledge/index.json`. Investigate and fix any latent corpus-specific issue surfaced by the shape test.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/knowledge/index.json`, `tests/repo/knowledge_index_shape.bats`, `tests/repo/knowledge_index_gitignore.bats`
**Commit**: `feat(knowledge-index): ship the initial knowledge/index.json`

### Step 7: PostToolUse hook — pattern matching + success feedback

**Complexity**: standard
**Maps to**: AC10, AC11, AC22 (PostToolUse half)
**RED**: `tests/hooks/knowledge_index_hook_tests.bats`:

- Doc-inspection: `settings.json` PostToolUse block contains an entry with `matcher: "Edit|Write"` invoking `bash hooks/knowledge-index.sh`.
- Behavioral: stdin shaped `{"tool_name":"Edit","tool_input":{"file_path":"plugins/agentic-dev-team/knowledge/owasp-detection.md"}}` → hook invokes a fake-bin shimmed `build-knowledge-index.sh` once (verified via sentinel file); stderr contains the literal `[knowledge-index] rebuilt`.
- Stdin with `file_path` under `agents/`, `commands/`, `docs/`, or any non-corpus path → hook exits 0 without invoking the builder shim AND emits no `[knowledge-index]` stderr.
- Stdin with `file_path` under `knowledge/schemas/` → hook exits 0 without invoking the builder (out-of-scope subdir).
- Stdin with `file_path` matching `skills/foo/SKILL.md` → hook invokes the builder and emits the rebuilt line.

**GREEN**: Create `plugins/agentic-dev-team/hooks/knowledge-index.sh`. Source `hooks/lib/knowledge-index-paths.sh` (Step 0 helper); resolve `BUILDER="${HOOK_DIR}/lib/build-knowledge-index.sh"` via `BASH_SOURCE` (matches the `agent-model-resolve.sh` pattern). Register in `settings.json` PostToolUse. Pattern match via `_is_corpus_path`; on match shell out to the builder and echo `[knowledge-index] rebuilt` to stderr on success.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/knowledge-index.sh`, `plugins/agentic-dev-team/settings.json`, `tests/hooks/knowledge_index_hook_tests.bats`
**Commit**: `feat(hooks): PostToolUse hook regenerates knowledge index on corpus edits`

### Step 8: PostToolUse hook — fail-open posture

**Complexity**: standard
**Maps to**: AC12
**RED**: Bats: with a fake-bin builder shim that exits 1 and writes "boom" to stderr, the hook (driven by valid corpus stdin) exits 0 and the hook's own stderr contains `[knowledge-index] rebuild failed`. The user's Edit completes successfully (hook does not block).
**GREEN**: Wrap the builder invocation: on success, echo `[knowledge-index] rebuilt`; on failure, echo `[knowledge-index] rebuild failed: <reason>`. Always `exit 0`.
**REFACTOR**: None.
**Files**: same as Step 7.
**Commit**: `feat(hooks): fail-open posture in knowledge-index PostToolUse hook`

### Step 9: Pre-commit gate — sibling PreToolUse:Bash hook + shared detection helper

**Complexity**: standard
**Maps to**: AC13, AC13a, AC14, AC15, AC22 (PreToolUse half)
**Restructured (design reviewer)**: a NEW sibling hook `hooks/pre-commit-knowledge-index.sh`, not an extension of `pre-commit-review.sh`. The two gates have independent concerns (review-pass vs index-freshness); sibling-hook keeps each file single-purpose. Also extracts the `git commit` detection idiom into a shared helper `hooks/lib/pre-commit-detect.sh` so both PreToolUse:Bash hooks consume one source of truth (parallel to Step 0's corpus-path helper).
**RED**: `tests/hooks/pre_commit_knowledge_index_tests.bats`. Four cases driven via a temp git repo + the existing `pre-commit-review.sh` `git commit` detection pattern:

- **AC13 (stale)**: stage `knowledge/foo.md` without re-staging `knowledge/index.json`; hook exits 2; stderr begins with the literal headline `knowledge/index.json is stale; the auto-rebuild ran but you must stage the result.`; stderr also contains both remediation lines `bash plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh` AND `git add plugins/agentic-dev-team/knowledge/index.json`.
- **AC13a (working-tree drift past staging)**: stage corpus + matching index, then re-edit the corpus working-tree file without re-staging; hook exits 2 with the same remediation. Verifies the working-tree-not-staged-content semantic.
- **AC14 (clean pass)**: stage both with no further edits; hook exits 0.
- **AC15 (skip)**: stage only `agents/security-review.md`; hook exits 0 and the builder is never invoked (fake-bin sentinel verifies).
- **AC22 (registration)**: `settings.json` PreToolUse Bash block contains an entry invoking `bash hooks/pre-commit-knowledge-index.sh`.

**GREEN**: First, extract `hooks/lib/pre-commit-detect.sh` from the existing `pre-commit-review.sh` — a single function `_is_git_commit_invocation` (reads the Bash PreToolUse stdin shape, fast-returns based on the same heuristic the current hook uses). Update `pre-commit-review.sh` to source this helper (small change; no behavioral diff). Add bats coverage in the existing `pre_commit_knowledge_index_tests.bats` that the helper returns 0 on `git commit` invocations and 1 otherwise.

Then create `hooks/pre-commit-knowledge-index.sh`:

1. Resolve `HOOK_DIR` from `BASH_SOURCE`; source `hooks/lib/knowledge-index-paths.sh` and `hooks/lib/pre-commit-detect.sh`; resolve `BUILDER="${HOOK_DIR}/lib/build-knowledge-index.sh"`. Same resolver pattern as the PostToolUse hook.
2. Call `_is_git_commit_invocation` from the shared helper; fast-exit on non-commit.
3. List staged files; filter via `_is_corpus_path`; if none, exit 0.
4. Invoke `bash "$BUILDER" --check`. On exit 0, exit 0. On non-zero, emit the two-line remediation heredoc and exit 2.

Register in `settings.json` PreToolUse Bash block alongside the existing `pre-commit-review.sh` entry.
**REFACTOR**: None — the helper extraction is part of GREEN, not a separate cleanup.
**Files**: `plugins/agentic-dev-team/hooks/pre-commit-knowledge-index.sh`, `plugins/agentic-dev-team/hooks/lib/pre-commit-detect.sh`, `plugins/agentic-dev-team/hooks/pre-commit-review.sh` (sources the new helper), `plugins/agentic-dev-team/settings.json`, `tests/hooks/pre_commit_knowledge_index_tests.bats`
**Commit**: `feat(hooks): pre-commit sibling hook + shared commit-detection helper`

### Step 9.5: jq version pin

**Complexity**: trivial
**Maps to**: AC24
**Why**: builder output stability depends on `jq >= 1.6` (`jq -c` whitespace consistency). Without a version floor, CI on older jq could flap the freshness gate.
**RED**: `tests/hooks/knowledge_index_jq_version_tests.bats`:

- Builder header documents the `jq >= 1.6` requirement.
- With `PATH` overridden to a `fake-bin/jq` shim that reports `jq-1.5`, the builder exits non-zero on first invocation; stderr contains `jq version` and names the floor.
- With the real `jq` (or a shim reporting `jq-1.6`+), the builder proceeds normally.

**GREEN**: Add a one-time version check at the top of the builder:

```bash
jq_version=$(jq --version 2>/dev/null | sed 's/jq-//')
case "$jq_version" in
  1.[6-9]*|2.*|[3-9].*) ;;
  *) echo "[knowledge-index] jq version $jq_version below required 1.6" >&2; exit 1 ;;
esac
```

**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh`, `tests/hooks/knowledge_index_jq_version_tests.bats`, `tests/hooks/fake-bin/jq` (new shim — only created during test setup, gitignored if persisted).
**Commit**: `feat(knowledge-index): pin jq >= 1.6 for stable output formatting`

### Step 10: CI freshness gate

**Complexity**: trivial
**Maps to**: AC16
**RED**: `tests/repo/knowledge_index_current.bats` — one test that runs `bash plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh --check` against the repo and asserts exit 0.
**GREEN**: Write the test. Index built in Step 6 should pass it on a clean tree.
**REFACTOR**: None.
**Files**: `tests/repo/knowledge_index_current.bats`
**Commit**: `test(knowledge-index): CI freshness gate`

### Step 11: Anchor-citation gate for agents (env-gated + per-cluster filterable)

**Complexity**: standard
**Maps to**: AC19
**Restructured (acceptance + strategic reviewers)**: the test is gated behind `KNOWLEDGE_SWEEP_DONE=1` so CI stays green throughout the per-cluster sweep. The test also supports an `AGENT_FILES` env-var filter — comma- or space-separated list of agent filenames — so each cluster step (12a/12b/12c) can verify just its scope locally. Step 12d removes the env-gate.
**RED**: `tests/agents/agent_knowledge_anchor_tests.bats`:

- `setup()` calls `skip` unless `KNOWLEDGE_SWEEP_DONE=1` is set. Default `bats tests/ -r` invocations see SKIP, not FAIL — CI stays green.
- The test reads `AGENT_FILES` (optional). When set, it's a whitespace- or comma-separated list of basenames (e.g., `security-review.md naming-review.md`). When unset, the test walks every file under `plugins/agentic-dev-team/agents/*.md`.
- **Typo guard**: every basename in `AGENT_FILES` must exist as a file under `plugins/agentic-dev-team/agents/`. If any does not exist, the test fails with `AGENT_FILES contains an unknown agent: <name>` — verified by a bats case that passes `AGENT_FILES="does-not-exist.md"` and asserts the failure message.
- For each match of `knowledge/[a-z-]+\.md` or `skills/[a-z-]+/SKILL\.md`:
  - If the reference has a `#anchor` fragment, assert the anchor exists in `knowledge/index.json` for that file.
  - Else, assert the same paragraph contains the **literal verbatim token** `Whole-file load:` (case-sensitive, hyphen, colon).
- On failure, the bats failure message quotes the required token verbatim so a contributor whose phrasing was off sees exactly what's missing.

**GREEN**: Write the gated test only. No agent edits yet.
**REFACTOR**: None.
**Files**: `tests/agents/agent_knowledge_anchor_tests.bats`
**Commit**: `test(agents): anchor-citation gate (skipped until KNOWLEDGE_SWEEP_DONE=1)`

### Step 12a: Agent sweep — security cluster

**Complexity**: complex
**Maps to**: AC19 (partial)
**Restructured (design reviewer)**: Step 12 was shotgun surgery — one cross-cutting commit touching ≈10 agent files with per-reference semantic judgment. Splitting per agent cluster makes each commit independently reviewable. Three clusters: security (security-review, security-engineer, codebase-recon, arch-review, domain-review), code quality (complexity-review, naming-review, structure-review, test-review, js-fp-review), and orchestration (orchestrator, architect, qa-engineer + any stragglers).
**Per-step verification**: each Step 12x runs the Step 11 bats test locally with `KNOWLEDGE_SWEEP_DONE=1` against only the files in that cluster — the test is parameterised over `AGENT_FILES` so each step has a passing local invocation. The final commit (Step 12d) removes the env-gate.

**RED**: With `KNOWLEDGE_SWEEP_DONE=1 AGENT_FILES="security-review.md security-engineer.md codebase-recon.md arch-review.md domain-review.md"`, the bats test fails for these files.
**GREEN**: For each reference in this cluster:

1. Look up the file in `knowledge/index.json`.
2. Identify the section the agent is actually drawing on (read the surrounding agent prose).
3. Append `#<anchor>` to the reference.
4. If the agent genuinely needs the whole file, append `Whole-file load: <one-sentence reason>` in the same paragraph.

Re-run the gated bats test; it must pass for this cluster. Inline review: `/review-agent spec-compliance-review` against this cluster.
**REFACTOR**: None.
**Files**: 5 agent files in the security cluster.
**Commit**: `refactor(agents): cite knowledge anchors in security cluster (12a)`

### Step 12b: Agent sweep — code quality cluster

**Complexity**: complex
**Maps to**: AC19 (partial)
**RED**: With `KNOWLEDGE_SWEEP_DONE=1 AGENT_FILES="complexity-review.md naming-review.md structure-review.md test-review.md js-fp-review.md"`, the bats test fails for these files.
**GREEN**: Same procedure as 12a, applied to the code-quality cluster.
**REFACTOR**: None.
**Files**: 5 agent files in the quality cluster.
**Commit**: `refactor(agents): cite knowledge anchors in code-quality cluster (12b)`

### Step 12c: Agent sweep — orchestration + stragglers

**Complexity**: complex
**Maps to**: AC19 (partial)
**RED**: With `KNOWLEDGE_SWEEP_DONE=1` and the remaining files in `AGENT_FILES`, the bats test fails.
**GREEN**: Sweep the orchestrator, architect, qa-engineer, and any other agent file with matching references. Confirm the full unfiltered run of the gated bats test passes (no remaining failures across all 10+ files).
**REFACTOR**: None.
**Files**: Remaining agent files (≈3–5).
**Commit**: `refactor(agents): cite knowledge anchors in orchestration cluster (12c)`

### Step 12d: Remove the env-gate; bats runs default

**Complexity**: trivial
**Maps to**: AC19 (finalize)
**RED**: With the env-gate still in place, default `bats tests/ -r` SKIPs the anchor test.
**GREEN**: Remove the `KNOWLEDGE_SWEEP_DONE=1` skip guard from the test's `setup()`. From this point forward the test runs by default and any new agent introducing a bare knowledge reference fails the suite.
**REFACTOR**: None.
**Files**: `tests/agents/agent_knowledge_anchor_tests.bats`
**Commit**: `test(agents): activate anchor-citation gate by default`

### Step 13: Builder performance gate (opt-in)

**Complexity**: standard
**Maps to**: AC23
**RED**: `tests/hooks/knowledge_index_perf_tests.bats` (gated by `KNOWLEDGE_INDEX_PERF=1`): 10 sequential rebuilds against the real corpus complete in < 10s wall-clock (1s per build ceiling).
**GREEN**: If the test fails, profile and trim — likely candidates: collapse multiple `jq` invocations into one pipeline, avoid per-section subshells, use `mapfile` for line buffering. If the test passes on first run, no GREEN work needed.
**REFACTOR**: None.
**Files**: `tests/hooks/knowledge_index_perf_tests.bats`, possibly `plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh`.
**Commit**: `feat(knowledge-index): performance gate + any necessary tightening`

### Step 14: No-extra-artifacts gate

**Complexity**: trivial
**Maps to**: AC21
**RED**: `tests/repo/knowledge_index_no_leak.bats`: after running `build-knowledge-index.sh` on a clean tree, `git status --porcelain` returns empty (no untracked files, no modifications other than potentially `knowledge/index.json` — which should also be unchanged on a clean tree).
**GREEN**: If the builder leaks temp files, sweep up. The Step 5 trap-based cleanup should already cover this.
**REFACTOR**: None.
**Files**: `tests/repo/knowledge_index_no_leak.bats`
**Commit**: `test(knowledge-index): no-leak gate`

### Step 15: Documentation — consumer usage pattern

**Complexity**: trivial
**Maps to**: spec §Agent consumer integration "Consumer usage pattern" requirement
**RED**: `tests/agents/orchestrator_index_pointer_test.bats`: the orchestrator's body contains a paragraph describing how to resolve a knowledge anchor (look up the section in `knowledge/index.json`, then Read with `offset`/`limit`).
**GREEN**: Add the canonical pointer paragraph (verbatim from the spec) to `agents/orchestrator.md`. Cross-reference it from `docs/agent-architecture.md` so contributors authoring new agents have a discoverable model.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/agents/orchestrator.md`, `plugins/agentic-dev-team/docs/agent-architecture.md`, `tests/agents/orchestrator_index_pointer_test.bats`
**Commit**: `docs(orchestrator): document the index lookup → section Read consumer pattern`

## Complexity Classification

| Step | Rating | Why |
|---|---|---|
| 0 | trivial | One regex constant + one function; pure helper |
| 1–5 | standard | New builder + bats; bounded surface; established patterns |
| 6 | standard | First integration of the builder against the real corpus; bumped from trivial per acceptance reviewer |
| 7, 8 | standard | New hook + settings.json change; mirrors `eval-compliance-check.sh` pattern |
| 9 | standard | New sibling PreToolUse:Bash hook; per-design-reviewer this is NOT an extension of `pre-commit-review.sh` |
| 9.5 | trivial | One version-check guard at the top of the builder |
| 10, 14, 15 | trivial | Assert a single property / drop in a documentation paragraph |
| 11 | standard | New bats gate, env-gated until Step 12d |
| 12a, 12b, 12c | complex | Per-cluster agent sweep with semantic judgment on each reference; each cluster is independently reviewable |
| 12d | trivial | Remove the env-gate from the bats test |
| 13 | standard | Opt-in perf gate; may require small builder tightening |

## Pre-PR Quality Gate

- [ ] All bats suites pass: `tests/hooks/`, `tests/agents/`, `tests/repo/` (the shape + gitignore + freshness + no-leak tests all live under `tests/repo/` — single test-tree location per design reviewer)
- [ ] Anchor test runs by default after Step 12d (no `KNOWLEDGE_SWEEP_DONE` env required)
- [ ] `settings.json` contains BOTH new hook registrations (the bats AC22 assertion verifies this, but it's worth a manual checklist line so a partial test run doesn't ship a missing registration): `PostToolUse.Edit|Write → hooks/knowledge-index.sh` AND `PreToolUse.Bash → hooks/pre-commit-knowledge-index.sh`
- [ ] Opt-in: `KNOWLEDGE_INDEX_PERF=1 bats tests/hooks/knowledge_index_perf_tests.bats` passes
- [ ] `/agent-audit` clean
- [ ] `/code-review` clean (no error/warning severity findings)
- [ ] Manual smoke: edit a knowledge file via the Edit tool; verify `knowledge/index.json` is auto-regenerated AND stderr shows `[knowledge-index] rebuilt`
- [ ] Manual smoke: rename a section header in a knowledge file but don't restage the index; `git commit` is blocked with the two-line remediation message
- [ ] Manual smoke: spot-check 2-3 sampled agent references per cluster (12a/12b/12c) — the anchor resolves to a real section in the index, and the section content matches the agent's stated need
- [ ] PR description references the spec, lists the three gate layers, names the corpus scope (knowledge + skills, excluding `docs/` and `knowledge/schemas/`), and links to the consumer usage pattern in `agents/orchestrator.md`

## Out of Scope (v1)

Inherited from spec §Out of Scope. Implementers must not expand this slice to include any of these:

- Indexing `docs/**.md`
- Fuzzy keyword search or `--query` mode on the builder
- Embedding-based retrieval
- Staged-content build mode for pre-commit (working tree is what `--check` compares)
- Automated/scripted rewrite of agent prose (Step 12 is a human-supervised sweep; future contributors are governed by the Step 11 bats gate)

## Risks & Open Questions

- **R1 — Anchor stability under section rename.** When a section header changes, every agent reference citing the old anchor breaks. Mitigation: the Step 11 bats gate (active after Step 12d) fails the rename PR; the renaming contributor must update consumers. This is the same coupling we already have for any prose reference; not a new problem.
- **R2 (RESOLVED)** — Builder `_first_sentence` precision is addressed by the operational sentence-boundary rule documented in the spec's §Builder section and tested by AC7a's parameterised cases.
- **R3 — Pre-commit gate friction.** Contributors who edit knowledge files but forget to re-stage `knowledge/index.json` will hit `exit 2` and need to `git add` the regenerated file. Mitigation: the PostToolUse hook auto-regenerates during the edit, so the file is already up-to-date when they `git add` later. The two-line remediation message explicitly names both the regen command AND `git add knowledge/index.json` so the recovery path is unambiguous.
- **R4 — Slug collisions across files.** GitHub-style slugs aren't globally unique; two different files can both have a section anchored `#overview`. Mitigation: anchors are scoped per file (the index nests sections under the file key), so within-file uniqueness (AC9) is sufficient. Cross-file collisions are not a problem because the reference syntax is `file.md#anchor`.
- **R5 (RESOLVED)** — Determinism under different `jq` versions is addressed by Step 9.5: the builder enforces `jq >= 1.6` with a clear error on older versions, and the header documents the floor.
- **R6 — Step 12 atomicity.** Splitting the agent sweep into three clusters (12a/12b/12c) plus the env-gate (Step 11 → 12d) means CI stays green throughout. The risk is that a contributor or reviewer forgets to remove the env-gate after 12c, leaving the test perpetually skipped. Mitigation: Step 12d is explicit and small; the Pre-PR Quality Gate's "Anchor test runs by default after Step 12d" checkbox catches the omission.

---

## Plan Review Summary

Three passes of plan-review personas (Acceptance, Design, UX, Strategic).

**Pass 1**: 3/4 needs-revision (Strategic approved). Major findings: AC7 sentence-boundary ambiguity, AC13/14 working-tree-vs-staged gap, Step 9 commit-gate conflation, Step 12 shotgun surgery, pre-commit error missing the `git add` step, PostToolUse silent success, `Whole-file load:` token not quoted in failure messages, missing consumer usage pattern.

**Pass 2**: 2/3 approve (Acceptance + UX); Design returned needs-revision over a stale spec section, a detection-helper coupling gap, and an `AGENT_FILES` env-contract gap. Resolved in this revision: spec stale section rewritten as a "reference implementation" pointer; `hooks/lib/pre-commit-detect.sh` extracted as a parallel to `knowledge-index-paths.sh`; Step 11 documents the `AGENT_FILES` filter with a typo-guard bats case.

**Pass 3**: Design approve. Two observations folded in non-blocking: the spec components table now lists `pre-commit-detect.sh` and the modified `pre-commit-review.sh`; Implementation Strategy bullet 3 rewritten to match Step 9's sibling-hook design.

Outstanding non-blocking observations:

- AC7a's parameterised table covers `.` terminators only; `!` and `?` are mentioned in the boundary algorithm but not tested. Tracked as a low-risk follow-on; current corpus has no observed `!`/`?`-terminated section summaries.
- The spec's reference-implementation code block (§Pre-commit gate: reference implementation) is illustrative only — the canonical contract is §Pre-commit gate (sibling hook). Implementers must read the prose, not paste the sketch.

**Status**: ready for human approval. 15 TDD steps (Steps 0–15 with 9.5 and 12a/b/c/d sub-numbering), 28 ACs across 4 freshness gates plus the agent-consumer integration.
