# Spec: On-Demand Knowledge Index

## Intent Description

Agents that reference `knowledge/**.md` or `skills/**/SKILL.md` today pay
for the whole file even when they only need one section. Discovery is
also weak — an agent that wants the OWASP A03 rule has no way to find it
short of reading `owasp-detection.md` end-to-end and grepping. The corpus
is small enough (≈45 markdown files, ≈4,600 lines) that the right tool
is a static index, not a search engine.

This slice ships `knowledge/index.json`: a deterministic, checked-in
catalog of every H2/H3 section across the two corpora, with each entry
holding a one-sentence summary and the section's slugified anchor.
Agents resolve "I want X" → "file Y, section #anchor-z" via a single
JSON lookup, then `Read` the file with `offset` and `limit` for just
that section. The index stays current via three defense-in-depth gates:
a PostToolUse hook regenerates on save, a pre-commit check refuses
stale commits, and a CI bats test catches anything that slips through.

Every agent today that references a knowledge file or SKILL is updated
to consult the index first. The change is mechanical: replace
"see `knowledge/owasp-detection.md`" with "see `knowledge/index.json` →
`knowledge/owasp-detection.md#a03-injection`" (or equivalent), so the
agent reads only the section it needs.

## User-Facing Behavior

```gherkin
Feature: On-demand knowledge index with freshness gates

  Background:
    Given the plugin ships knowledge/index.json built from knowledge/**.md and skills/**/SKILL.md
    And every H2 and H3 section in those files appears as one entry in the index
    And each entry has exactly two fields: "summary" (one sentence) and "anchor" (slugified header)
    And entries are keyed by relative file path then header text

  # --- Index shape and determinism ---

  Scenario: Index file exists and parses as JSON
    Given the plugin source tree is checked out clean
    When jq -e . knowledge/index.json runs
    Then the exit code is 0

  Scenario: Index entry has minimal shape
    Given the index contains an entry for knowledge/owasp-detection.md
    When the entry for the "A03 Injection" section is read
    Then it has exactly two fields: summary, anchor
    And summary is a single sentence ending in a period
    And anchor matches the slugified header text (lowercase, hyphens for spaces, no punctuation)

  Scenario: Index is deterministic across rebuilds
    Given the index has just been rebuilt
    When the index is rebuilt a second time with no source changes
    Then knowledge/index.json is byte-identical to the prior build
    And no generated_at, timestamp, or build_id field appears anywhere in the file

  Scenario: Index keys and entries are sorted
    Given knowledge/index.json
    When the keys are inspected
    Then file paths appear in lexicographic order
    And sections within each file appear in source order (top to bottom in the markdown)

  Scenario: Index covers both corpora
    Given knowledge/owasp-detection.md and skills/specs/SKILL.md both exist
    When knowledge/index.json is read
    Then both files appear as top-level keys
    And neither file under docs/ appears (out of scope for v1)

  # --- Freshness gate: PostToolUse hook ---

  Scenario: Editing a knowledge file via Claude Code regenerates the index
    Given the user runs an Edit on knowledge/owasp-detection.md changing a section header
    When the Edit tool completes
    Then knowledge/index.json is updated to reflect the renamed section
    And the rebuild emits one line to stderr beginning with "[knowledge-index]"
    And the user's Edit reports success

  Scenario: Editing an unrelated file does not regenerate the index
    Given the user runs an Edit on plugins/agentic-dev-team/agents/security-review.md
    When the PostToolUse hook fires
    Then hooks/knowledge-index.sh exits 0 without touching knowledge/index.json
    And the index file mtime is unchanged

  Scenario: PostToolUse hook fails open
    Given hooks/lib/build-knowledge-index.sh exits non-zero for any reason
    When the PostToolUse hook runs
    Then the hook exits 0
    And the failure is logged to stderr with a "[knowledge-index]" tag
    And the user's Edit completes successfully

  # --- Freshness gate: pre-commit check ---

  Scenario: Pre-commit check passes when working-tree index matches sources
    Given the user has staged knowledge/owasp-detection.md and knowledge/index.json
    And the working-tree knowledge/index.json matches what a fresh build of the working tree would produce
    When the pre-commit hook fires on git commit
    Then the check exits 0 and the commit proceeds

  Scenario: Pre-commit check blocks a commit with a stale working-tree index
    Given the user has staged knowledge/owasp-detection.md without restaging the index
    And the working-tree knowledge/index.json does not match what a fresh build of the working tree would produce
    When the pre-commit hook fires on git commit
    Then the check exits 2
    And stderr contains the line "knowledge/index.json is stale; the auto-rebuild ran but you must stage the result."
    And stderr contains the two-line remediation:
      """
        1. bash plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh
        2. git add plugins/agentic-dev-team/knowledge/index.json
      """
    And the commit is blocked

  Scenario: Pre-commit catches working-tree drift even when the staged pair is consistent
    Given the user has staged knowledge/owasp-detection.md and knowledge/index.json
    And after staging the user re-edited knowledge/owasp-detection.md without re-staging
    When the pre-commit hook fires on git commit
    Then the check exits 2 with the same stderr remediation as the stale-index scenario
    And the commit is blocked

  Scenario: Pre-commit check is skipped when no indexed file is staged
    Given the user has staged plugins/agentic-dev-team/agents/security-review.md
    And no knowledge/**.md or skills/**/SKILL.md file is staged
    When the pre-commit hook fires
    Then the index freshness check is skipped silently and the commit proceeds

  # --- Freshness gate: CI bats test ---

  Scenario: Bats freshness gate passes on a clean checkout
    Given a clean checkout of the repo with no local edits
    When tests/repo/knowledge_index_current.bats runs
    Then the test exits 0

  Scenario: Bats freshness gate fails when index is stale
    Given a knowledge file has been edited and knowledge/index.json was not rebuilt
    When tests/repo/knowledge_index_current.bats runs
    Then the test exits non-zero
    And the failure message names the regeneration command

  # --- Builder modes ---

  Scenario: --check mode reports stale without writing
    Given knowledge/index.json is stale by one section header rename
    When build-knowledge-index.sh --check runs
    Then the script exits non-zero
    And no file is written or modified under knowledge/
    And stderr contains a unified diff of expected vs actual index content

  Scenario: --check mode reports current
    Given knowledge/index.json matches what a rebuild would produce
    When build-knowledge-index.sh --check runs
    Then the script exits 0
    And produces no stderr output

  Scenario: Default mode rebuilds in place
    Given knowledge/index.json is stale
    When build-knowledge-index.sh runs with no arguments
    Then knowledge/index.json is overwritten with the rebuilt content
    And the script exits 0

  # --- Agent consumer integration ---

  Scenario: Agents that reference knowledge files cite a section anchor
    Given an agent's body references "knowledge/owasp-detection.md"
    When the reference is read
    Then it names a specific section anchor (e.g., "knowledge/owasp-detection.md#a03-injection")
    AND the anchor exists in knowledge/index.json for that file
    OR the paragraph containing the reference includes the literal token "Whole-file load:" followed by a one-sentence rationale

  Scenario: Agents are not required to use the index for files outside the corpus
    Given an agent references a file under docs/ (e.g., docs/model-routing.md)
    When the reference is read
    Then no anchor is required and no test enforces one
    And the index does not contain that file

  # --- Migration / no leaks ---

  Scenario: Index file is checked into git
    Given knowledge/index.json exists in the working tree
    When git ls-files knowledge/index.json runs
    Then exit code is 0 and the file is listed
    And .gitignore does not exclude it

  Scenario: Per-user build artifacts do not leak
    Given the build script produces no temp or cache files outside knowledge/index.json
    When git status runs after a rebuild
    Then no untracked files appear under knowledge/ or hooks/lib/
```

## Architecture Specification

### Components changed or added

| File | Status | Purpose |
|---|---|---|
| `plugins/agentic-dev-team/knowledge/index.json` | NEW | Checked-in deterministic index over `knowledge/**.md` + `skills/**/SKILL.md` |
| `plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh` | NEW | Builder. Modes: default (write), `--check` (verify, no write) |
| `plugins/agentic-dev-team/hooks/lib/knowledge-index-paths.sh` | NEW | Shared helper exporting the corpus regex + `_is_corpus_path` function. Sourced by all three callers (PostToolUse hook, pre-commit gate, anchor-citation test) |
| `plugins/agentic-dev-team/hooks/lib/pre-commit-detect.sh` | NEW | Shared helper exporting `_is_git_commit_invocation` (extracted from `pre-commit-review.sh` so both PreToolUse:Bash hooks consume one source of truth) |
| `plugins/agentic-dev-team/hooks/pre-commit-review.sh` | MODIFIED | Source the new `pre-commit-detect.sh` helper; no behavioral change |
| `plugins/agentic-dev-team/hooks/knowledge-index.sh` | NEW | PostToolUse hook on `Edit\|Write`; regenerates the index when a corpus file is touched |
| `plugins/agentic-dev-team/hooks/pre-commit-knowledge-index.sh` | NEW | Sibling PreToolUse `Bash` hook (separate from `pre-commit-review.sh`). Blocks `git commit` when the working-tree index does not match what a build of the working tree would produce |
| `plugins/agentic-dev-team/settings.json` | MODIFIED | Registers `hooks/knowledge-index.sh` under `PostToolUse.matcher = "Edit\|Write"` AND `hooks/pre-commit-knowledge-index.sh` under `PreToolUse.matcher = "Bash"` |
| `plugins/agentic-dev-team/agents/*.md` (~10 files referencing knowledge) | MODIFIED | Replace bare `knowledge/<file>.md` references with `knowledge/<file>.md#<anchor>` based on the new index |
| `tests/repo/knowledge_index_current.bats` | NEW | CI freshness gate |
| `tests/repo/knowledge_index_shape.bats` | NEW | Real-corpus shape assertions (coverage, no extras) |
| `tests/repo/knowledge_index_no_leak.bats` | NEW | `git status` clean after a rebuild |
| `tests/repo/knowledge_index_gitignore.bats` | NEW | AC20: file is tracked and not gitignored |
| `tests/hooks/knowledge_index_builder_tests.bats` | NEW | Builder behavior (default + `--check`; determinism; sort order; corpus scope) |
| `tests/hooks/knowledge_index_hook_tests.bats` | NEW | PostToolUse hook routing, fail-open posture, scope filter |
| `tests/hooks/pre_commit_knowledge_index_tests.bats` | NEW | Pre-commit sibling hook behavior |
| `tests/agents/agent_knowledge_anchor_tests.bats` | NEW | Each in-scope agent reference cites an anchor that exists in the index |

### Index file shape

`knowledge/index.json` is a single JSON object keyed by repo-relative
path, then by section header text. The minimal entry has exactly two
fields:

```json
{
  "plugins/agentic-dev-team/knowledge/owasp-detection.md": {
    "A03 Injection": {
      "summary": "Detection patterns for SQL, NoSQL, OS command, and ORM injection vectors.",
      "anchor": "a03-injection"
    },
    "A07 Authentication failures": {
      "summary": "Session, credential, and MFA-related failure modes.",
      "anchor": "a07-authentication-failures"
    }
  },
  "plugins/agentic-dev-team/skills/specs/SKILL.md": {
    "Cross-Artifact Consistency Gate": {
      "summary": "Validate all four artifacts as a set before implementation begins.",
      "anchor": "cross-artifact-consistency-gate"
    }
  }
}
```

Rules:

- Top-level keys are repo-relative file paths, sorted lexicographically.
- Section keys are the header text verbatim, ordered by source position.
- `summary` is the first sentence of the section body, ending in `.`. If
  the section has no body (e.g., only sub-headers), summary is the first
  sentence of the first child section.
- `anchor` is the GitHub-flavored slug: lowercase, spaces → hyphens,
  punctuation stripped, no leading/trailing hyphens.
- No timestamp, no `generated_at`, no build counter. Determinism is a
  hard requirement.

### Builder

`hooks/lib/build-knowledge-index.sh`:

- Default mode (no args): rebuilds `knowledge/index.json` from sources in place.
- `--check` mode: rebuilds in a tempdir, diffs against the on-disk
  `index.json`, exits 0 on match and non-zero on drift. Stderr carries
  the unified diff. No file is written or modified.
- Inputs: walk `knowledge/**.md` (top-level only — `knowledge/schemas/`
  is excluded) and `skills/**/SKILL.md`. Skip non-markdown, skip
  `index.json` itself, skip anything not under those two trees.
- Section extraction: H2 (`##`) and H3 (`###`) headers. H1 is the file
  title, not indexed. H4+ are not indexed (keeps entries coarse-grained;
  agents who need finer scopes Read the file).
- Summary extraction: first non-blank, non-list, non-code line under the
  header. If only lists/code follow until the next header, summary is
  the first list item's text (trimmed).
- Sentence-boundary rule (precise, deterministic): a sentence ends at
  the first `.`, `!`, or `?` that is followed by either whitespace or
  end-of-line, AND is not preceded by a single uppercase letter
  (handles initials like `J. Doe`) or one of the literal abbreviation
  tokens `e.g`, `i.e`, `etc`, `vs`, `Mr`, `Mrs`, `Ms`, `Dr`, `Jr`, `Sr`,
  `St`, `No`, `cf`. If no terminator is found within 240 characters,
  the summary is truncated at the last whitespace before 240 chars and
  a trailing `…` is appended.
- Environment variables (TEST-ONLY injection seams, documented as such
  in the header comment block — never user-facing):
  `KNOWLEDGE_INDEX_CORPUS_ROOTS` (override corpus walk root),
  `KNOWLEDGE_INDEX_OUTPUT` (override on-disk output path). Production
  callers never set these.
- `jq` requirement: `jq >= 1.6`. Builder runs `jq --version` at start
  and exits with a clear error if the version is older. The version
  floor is also documented in the header comment.

### Shared corpus-path helper

`hooks/lib/knowledge-index-paths.sh` exports a single function
`_is_corpus_path <path>` and the regex it uses. The PostToolUse hook,
the pre-commit hook, and the anchor-citation bats test all source this
file rather than duplicating the pattern. A future scope change is a
one-file edit.

### PostToolUse hook

`hooks/knowledge-index.sh`:

- Registered under `PostToolUse` with `matcher: "Edit|Write"`.
- Resolves `BUILDER="${HOOK_DIR}/lib/build-knowledge-index.sh"` and
  sources `${HOOK_DIR}/lib/knowledge-index-paths.sh` (matches the
  `agent-model-resolve.sh` precedent).
- Reads stdin (Claude Code hook contract: `tool_name`, `tool_input.file_path`).
- Calls `_is_corpus_path` to decide whether to act.
- On match: invokes the builder, then emits one line to stderr
  `[knowledge-index] rebuilt` on success. On any builder failure
  (script error, jq error, disk full, …), exits 0 and emits a
  `[knowledge-index] rebuild failed: <reason>` stderr line. Fail-open
  posture per repo convention.
- On no match: exits 0 immediately, no I/O.

### Pre-commit gate (sibling hook)

`hooks/pre-commit-knowledge-index.sh` is a separate `PreToolUse:Bash`
hook, not an extension of `hooks/pre-commit-review.sh`. The two gates
have independent concerns (review-pass vs index-freshness) and the
sibling-hook pattern keeps each file single-purpose.

Behavior:

1. Detect a `git commit` Bash invocation; fast-exit silently if not a
   commit (mirrors the `pre-commit-review.sh` detection pattern).
2. List staged files (`git diff --cached --name-only --diff-filter=ACMR`).
3. Use `_is_corpus_path` (from the shared helper) to filter for corpus
   matches. If none, exit 0 silently.
4. Otherwise invoke `build-knowledge-index.sh --check` against the
   working tree.
5. On `--check` exit 0: exit 0 silently — commit proceeds.
6. On `--check` non-zero: emit the two-line remediation block (see
   spec scenario "Pre-commit check blocks") and exit 2.

Working-tree (not staged content) is the comparison surface — the
PostToolUse hook ensures the working-tree index is current on every
Edit, so the contributor's only remaining job is to `git add` it. The
sibling hook's remediation message makes this explicit.

### Pre-commit gate: reference implementation

The full behavioral contract lives in §Pre-commit gate (sibling hook)
above. Reference sketch of the new `hooks/pre-commit-knowledge-index.sh`
body (illustrative only — the canonical description is the prior
section):

```bash
#!/usr/bin/env bash
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HOOK_DIR}/lib/knowledge-index-paths.sh"
source "${HOOK_DIR}/lib/pre-commit-detect.sh"   # shared git-commit detection (Step 9 warning)
BUILDER="${HOOK_DIR}/lib/build-knowledge-index.sh"

_is_git_commit_invocation || exit 0

staged=$(git diff --cached --name-only --diff-filter=ACMR)
corpus=$(echo "$staged" | grep -E "$CORPUS_REGEX" || true)
[[ -z "$corpus" ]] && exit 0

if ! err=$(bash "$BUILDER" --check 2>&1); then
  cat >&2 <<EOF
knowledge/index.json is stale; the auto-rebuild ran but you must stage the result.

  1. bash plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh
  2. git add plugins/agentic-dev-team/knowledge/index.json
EOF
  echo "$err" >&2
  exit 2
fi
```

`build-knowledge-index.sh --check` operates against the **working
tree**, not staged content. Rationale: the PostToolUse hook keeps the
working-tree index current; the contributor's only remaining task is
`git add`. The remediation message captures this so the contributor is
never left guessing why a re-run of the builder alone didn't fix the
block.

Out-of-scope for v1: a "staged-content build" mode. Note the explicit
scenario `Pre-commit catches working-tree drift even when the staged
pair is consistent` — the gate fires whenever the working tree diverges
from a fresh build, even if a previously-staged pair was internally
consistent.

### CI freshness gate

`tests/repo/knowledge_index_current.bats`:

```bash
@test "knowledge/index.json is current" {
  cd "$REPO_ROOT"
  run bash plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh --check
  [ "$status" -eq 0 ]
}
```

This is part of the standard `bats tests/ -r` invocation and runs in
`/pr` and any CI workflow that already executes the suite.

### Agent consumer integration

Each in-scope agent body that references `knowledge/<file>.md` or
`skills/<name>/SKILL.md` is updated to cite an anchor. The mechanical
test (`tests/agents/agent_knowledge_anchor_tests.bats`) walks every agent
file under `agents/`, extracts every reference matching
`knowledge/[a-z-]+\.md` or `skills/[a-z-]+/SKILL\.md`, and asserts the
reference either:

1. Includes a `#<anchor>` fragment, AND the anchor exists in the index
   for that file; OR
2. Is followed within the same paragraph by the **literal token**
   `Whole-file load:` (case-sensitive, including the hyphen and colon)
   followed by a one-sentence rationale explaining why the section-level
   reference doesn't apply.

When the test fails, its error message quotes the required token
verbatim so a contributor whose phrasing was off (e.g., `Whole file
load:` without the hyphen) sees exactly what's missing.

**Consumer usage pattern** (for agents reading the index): every
agent's body whose work involves looking up knowledge references
includes a one-line pointer near the top of its body:

> Knowledge references in this file cite a section anchor (e.g.
> `knowledge/owasp-detection.md#a03-injection`). Resolve the anchor via
> `knowledge/index.json` (the section's `summary` describes what's in
> it), then Read the file with `offset` and `limit` for just that
> section.

This sentence ships in the orchestrator's body once (as the canonical
explanation) and via short cross-reference in any agent that consumes
knowledge files. The bats anchor-citation gate does not enforce the
pointer's presence — it's a doc-discipline convention, not a contract.

Out of scope for v1: programmatically adjusting agent prose. The
mechanical update is done as part of this slice's build steps (under
careful review), but it is not part of the long-term gate — future
contributors writing new agents are subject to the bats test.

### Constraints

- **Determinism**: the index file is byte-identical across rebuilds when
  inputs are unchanged. Verified by the freshness gate.
- **No timestamps, no build IDs.** Diffs are only signal when content
  changes.
- **Fail-open hooks**: PostToolUse never blocks an edit; pre-commit
  blocks only with `exit 2` and a clear remediation line.
- **No new dependencies**: bash + jq + git. Already required.
- **Encoding**: index is UTF-8, LF line endings, ends with a newline.

### Out of scope (v1)

- Indexing `docs/**.md` (project documentation; overlaps with CLAUDE.md
  catalog role).
- Fuzzy keyword search across summaries (premature; corpus is small).
- Embedding-based retrieval (premature; corpus is small).
- Staged-content build mode for the pre-commit gate (working tree is
  what `--check` compares; contributors stage the index alongside).
- A `--list` or `--query` mode on the builder for ad-hoc lookups; the
  index is consumed via standard JSON tooling.
- Automated rewrite of agent prose to cite anchors; the slice does this
  manually for current agents and locks in the rule for future ones via
  the bats gate.

## Acceptance Criteria

| # | Criterion | Pass condition |
|---|---|---|
| AC1 | Index file exists and parses | `jq -e . plugins/agentic-dev-team/knowledge/index.json` exits 0 |
| AC2 | Minimal entry shape | Bats: every entry has exactly the keys `summary` and `anchor`; no other keys appear anywhere in the index |
| AC3 | Determinism | Bats: build twice with no source changes; `cmp` reports byte-identical |
| AC4 | No timestamps | Bats: `grep -E '(generated_at\|timestamp\|build_id\|"date"\|"updated")' index.json` returns no matches |
| AC5 | Sort order | Bats: top-level keys are lexicographically sorted; per-file sections appear in source-position order (verified by re-extracting source positions and comparing) |
| AC6 | Corpus coverage | Bats: every `knowledge/*.md` (excluding `knowledge/schemas/`) and every `skills/*/SKILL.md` appears as a top-level key; no file outside that corpus appears |
| AC7 | Summary shape | Bats: every `summary` is non-empty, has ≥ 8 characters, and is produced by the §Builder sentence-boundary rule (verified by feeding each fixture through `_first_sentence` and asserting `==` against the index entry's summary) |
| AC7a | Sentence-boundary correctness | Bats: parameterised cases for `e.g.`/`i.e.`/`Mr.`/`J. Doe`/single-uppercase + period/240-char truncation. Each input produces the documented expected summary, terminating only at a true boundary |
| AC8 | Anchor shape | Bats: every `anchor` matches `^[a-z0-9][a-z0-9-]*[a-z0-9]$` (slugified GitHub style) |
| AC9 | Anchor uniqueness within a file | Bats: no two sections within the same file share an anchor. Includes an H2/H3 fixture with two identically-named sections to verify the disambiguation suffix (`-1`, `-2`) matches GitHub-style |
| AC10 | PostToolUse rebuilds on corpus edit | Bats: simulate `Edit` on `knowledge/foo.md`; hook invokes the builder once; index is rebuilt; stderr contains `[knowledge-index] rebuilt` |
| AC11 | PostToolUse ignores unrelated edits | Bats: simulate `Edit` on `agents/security-review.md`; hook exits 0 and index file mtime is unchanged; no `[knowledge-index]` stderr |
| AC12 | PostToolUse fail-open | Bats: with the builder forced to exit 1 via a shim, hook still exits 0 and stderr contains `[knowledge-index] rebuild failed` |
| AC13 | Pre-commit block on stale index | Bats: stage a corpus file edit without re-staging the index; `pre-commit-knowledge-index.sh` exits 2; stderr contains both the headline `knowledge/index.json is stale; the auto-rebuild ran but you must stage the result.` and the two-line remediation (`bash ... build-knowledge-index.sh` then `git add ... knowledge/index.json`) |
| AC13a | Pre-commit catches working-tree drift past the staged pair | Bats: stage corpus + matching index, then re-edit the corpus without re-staging; hook exits 2 with the same remediation. Verifies the working-tree-not-staged-content semantic is enforced |
| AC14 | Pre-commit passes when working-tree is clean | Bats: stage corpus + index together with no further edits; hook exits 0 |
| AC15 | Pre-commit skip when irrelevant | Bats: stage only `agents/security-review.md`; hook exits 0 without invoking the builder (verified via shim sentinel) |
| AC16 | CI freshness gate | `tests/repo/knowledge_index_current.bats` runs `build-knowledge-index.sh --check`; exit 0 on a clean tree |
| AC17 | `--check` is read-only | Bats: file-tree sha256 before/after `--check` invocation is identical |
| AC17a | `--check` clean run is silent | Bats: with the on-disk index current, `--check` exit 0 produces zero bytes on stderr and zero bytes on stdout |
| AC18 | `--check` diff output on drift | Bats: with index forcibly stale, `--check` stderr contains a `---` / `+++` / `@@` unified diff |
| AC19 | Agent references cite anchors | Bats: every `knowledge/X.md` or `skills/Y/SKILL.md` reference in `agents/**.md` either has a `#anchor` fragment whose anchor exists in `knowledge/index.json` for that file, OR the same paragraph contains the **verbatim literal token** `Whole-file load:` (case-sensitive, hyphen, colon) followed by a non-empty sentence. The bats failure message quotes the required token literally |
| AC20 | Index is git-tracked | `git ls-files plugins/agentic-dev-team/knowledge/index.json` returns the path AND `git check-ignore plugins/agentic-dev-team/knowledge/index.json` exits non-zero (verified by `tests/repo/knowledge_index_gitignore.bats`) |
| AC21 | No extra build artifacts | Bats: `git status --porcelain` after a clean rebuild on a clean tree contains no untracked or modified files |
| AC22 | Settings registration | Bats: `plugins/agentic-dev-team/settings.json` PostToolUse block has an entry with `matcher: "Edit\|Write"` invoking `bash hooks/knowledge-index.sh` AND PreToolUse Bash block has an entry invoking `bash hooks/pre-commit-knowledge-index.sh` |
| AC23 | Builder rebuild performance | Bats (opt-in via `KNOWLEDGE_INDEX_PERF=1`): 10 sequential rebuilds complete in < 10s wall-clock (1s per build ceiling) |
| AC24 | jq version floor | Bats: builder header documents `jq >= 1.6` requirement AND the builder exits non-zero with a clear `jq version` error when run against a shimmed `jq` reporting `1.5` |

## Consistency Gate

- [x] **Intent unambiguous**: two developers reading the intent would
  both build a static JSON index keyed by file path then header, with
  determinism as a hard property and three escalating freshness gates.
- [x] **Every behavior has a scenario**: index shape, determinism,
  sort, corpus coverage, PostToolUse fire, PostToolUse fail-open,
  pre-commit block, pre-commit pass, pre-commit skip, CI gate fail,
  CI gate pass, `--check` read-only, `--check` diff, agent anchor
  citation, no-leak — all covered.
- [x] **Architecture constrains without over-engineering**: builder is
  one bash script; index is one JSON file; three hook touchpoints;
  ~10 agent files updated. No new dependencies. No new daemon. No
  embedding store.
- [x] **Terminology consistent**: "index", "corpus" (knowledge + skills),
  "anchor", "section", "freshness gate", "builder", `--check`,
  "fail-open" used uniformly across artifacts.
- [x] **No contradictions**: the index is checked in (AC20), built
  deterministically (AC3), and never carries timestamps (AC4). Hooks
  fail open at runtime but the CI gate is strict — three layers, not
  three contradictions.

**Verdict: PASS.** Proceeding to `/plan`.
