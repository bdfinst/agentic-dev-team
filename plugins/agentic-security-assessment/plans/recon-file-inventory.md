# Plan: RECON envelope `file_inventory` (Gap 6a)

**Created**: 2026-04-24
**Revised**: 2026-04-24 (post plan-review v1 — addresses 6 blockers)
**Approved**: 2026-04-24 (user approval; in-plan path references will need a short update pass after the plugin rename lands)
**Branch**: main
**Status**: approved (v2)
**Spec**: `plugins/agentic-security-assessment/docs/specs/recon-file-inventory.md`
**Source prompt**: `.prompts/close-gaps-vs-opus-repo-scan.md` (Gap 6a, precondition of Gap 6)

## Goal

Extend the RECON envelope (primitives contract 1.2.0, MINOR) with an optional `file_inventory` field backed by a sibling file `memory/recon-<slug>.inventory.txt`. This closes the precondition for Gap 6 (forbid LLM tree re-walks): the hook Gap 6 introduces needs an authoritative, complete list of files the recon considered in scope, and the current envelope does not provide one. Field ships as a sibling file (not embedded) because large repos produce 10k+ paths that bloat JSON diffs and validation cost. Cross-plugin: implementation lives in `plugins/agentic-dev-team/` (envelope owner) even though the spec file is colocated with Gap 6 under `plugins/agentic-security-assessment/`.

## Key design decisions (resolved)

Locked before implementation to prevent drift (these were open questions in v1; v1 plan review flagged them as blockers):

1. **Single source of truth for the enumeration pipeline.** The canonical, shippable implementation lives at `plugins/agentic-dev-team/scripts/recon-inventory.sh`. The `codebase-recon` agent prompt invokes this script. Test harnesses invoke the same script. No duplication of the pipeline anywhere.
2. **Single source of truth for the exclude list.** Excluded prefixes and filenames (filesystem-walk branch) live in `plugins/agentic-dev-team/knowledge/recon-inventory-excludes.txt`, one entry per line, with `# prefix:` and `# filename:` section markers. The script reads this file; the contract doc and the agent prompt cross-reference it. Both files ship with the plugin (no runtime dependency on the `evals/` tree).
3. **Consumer error contract for the sibling file.** The contract doc (`security-primitives-contract.md`) states explicitly: consumers that need the inventory (e.g., Gap 6's hook) **must fail-open** when (a) the envelope lacks `file_inventory`, (b) the sibling file is absent, or (c) `count != wc -l` of the sibling. Fail-open = emit a one-time informational notice and proceed without the check. This is enforced by Step 6's backward-compat test.
4. **AC-11 is enforced at the pipeline level, not the 10k-repo level.** The plan's gating performance test measures `scripts/recon-inventory.sh` on the polyglot fixture and asserts a concrete CI-measurable budget (<200 ms p95 on commodity hardware). The spec's 10k-repo claim becomes an observational measurement attached to the PR description, captured with `time` against a real dogfood target.

## Acceptance Criteria

Directly from the spec (AC-1 … AC-12), with AC-11 re-scoped per decision #4 above, AC-10 extended to cover fail-open, and a new AC-13 for the resolved error contract.

- [ ] AC-1: `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` header shows version 1.2.0 and Changelog entry documents the addition
- [ ] AC-2: `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json` declares optional `file_inventory` object with `source`, `count`, `sibling_ref`
- [ ] AC-3: `evals/codebase-recon/expected-schema.json` bumps `schema_version` const to `"0.2"` and adds the optional `file_inventory` object
- [ ] AC-4: On a git target, `memory/recon-<slug>.inventory.txt` exists; sorted (`LC_ALL=C`); deduped; LF-terminated; no blank lines
- [ ] AC-5: Main envelope's `file_inventory.count == wc -l <sibling>`; `sibling_ref` matches basename
- [ ] AC-6: Non-git fallback walk excludes every prefix and filename listed in `knowledge/recon-inventory-excludes.txt`
- [ ] AC-7: Submodule gitlink appears once; no recursive descent (verified by a fixture with a submodule)
- [ ] AC-8: Only real-path symlink targets appear; no double-count; broken links recorded to envelope `notes`
- [ ] AC-9: `ts-monorepo` and `polyglot` fixtures each ship `expected-inventory.txt` + `expected-file-inventory.json`; regeneration is byte-identical
- [ ] AC-10: Pre-1.2.0 sample envelope still validates against the 1.2.0 schema
- [ ] AC-10a (new): A consumer-stub test loads a pre-1.2.0 envelope, detects absent `file_inventory`, and follows the documented fail-open path (one-time notice, proceed)
- [ ] AC-11 (re-scoped): `scripts/recon-inventory.sh` on the polyglot fixture completes in <200 ms p95 on commodity hardware, asserted by `evals/codebase-recon/tests/inventory-budget.sh`
- [ ] AC-12: Gap 6 hook can reference `file_inventory.sibling_ref` without further negotiation — demonstrated by a shape-freeze fixture (`evals/primitives-contract/fixtures/file-inventory-consumer-contract.json`) asserting the four required properties and their types
- [ ] AC-13 (new): Consumer error contract for missing-sibling / count-mismatch / missing-field documented in `security-primitives-contract.md` under the Envelope 1 subsection, matching the three branches in decision #3

## User-Facing Behavior

Verbatim from the spec, plus three scenarios added at plan level to close gaps flagged in review (these are plan-level test targets; the spec should be amended in a follow-up to keep the two in sync — noted in Risks).

```gherkin
Feature: RECON envelope carries an authoritative file inventory

  Scenario: Git target — inventory from git ls-files
    Given the target repo is a git working tree
    When codebase-recon runs to completion
    Then memory/recon-<slug>.inventory.txt exists
    And each line is a repo-relative path, LF-terminated, no blank lines
    And the file is sorted lexicographically (LC_ALL=C byte order) and deduplicated
    And the main envelope's file_inventory.source == "git-ls-files"
    And the main envelope's file_inventory.count == line count of the sibling
    And the main envelope's file_inventory.sibling_ref == "recon-<slug>.inventory.txt"

  Scenario: Non-git target — filesystem walk with standard excludes
    Given the target is not a git repo
    When codebase-recon runs
    Then file_inventory.source == "filesystem-walk"
    And the walk excludes prefixes and filenames listed in plugins/agentic-dev-team/knowledge/recon-inventory-excludes.txt
    And every other regular file under repo root appears in the inventory

  Scenario: Submodules (git target)
    Given the target has a submodule at "vendor/plugin-x"
    When codebase-recon runs
    Then the inventory lists "vendor/plugin-x" exactly once as the gitlink entry
    And it does NOT recurse into the submodule's contents

  Scenario: Symlinks
    Given a symlink "src/alias.ts" -> "src/handlers/auth.ts"
    When codebase-recon runs
    Then the inventory lists the resolved target "src/handlers/auth.ts" once
    And "src/alias.ts" is not an independent entry
    And a broken symlink is skipped and noted in the envelope's notes array

  Scenario: Backward compatibility with pre-1.2.0 envelopes
    Given a RECON envelope produced before 1.2.0
    When validated against recon-envelope-v1.json (v1.2.0)
    Then validation passes (file_inventory is optional)

  Scenario: Consumer fail-open on missing sibling (plan-level, amend spec)
    Given an envelope with file_inventory but the sibling file is absent
    When a consumer-stub runs the documented fail-open path
    Then the stub emits a one-time "sibling missing" notice to stderr
    And the stub proceeds without the membership check

  Scenario: Consumer fail-open on count mismatch (plan-level, amend spec)
    Given an envelope with file_inventory.count != line count of sibling
    When a consumer-stub runs the documented fail-open path
    Then the stub emits a one-time "count mismatch" notice
    And proceeds without the check

  Scenario: Empty repo (plan-level, amend spec)
    Given a git repo with zero tracked files
    When codebase-recon runs
    Then the sibling file exists and is zero bytes
    And file_inventory.count == 0

  Scenario: Contract version bump
    Then plugins/agentic-dev-team/knowledge/security-primitives-contract.md declares version 1.2.0
    And the Changelog section documents the addition
    And consumers declaring required-primitives-contract: ^1.0.0 install unmodified

  Scenario: v0.1 placeholder schema mirrors the addition
    Then evals/codebase-recon/expected-schema.json bumps schema_version const to "0.2"
    And file_inventory is added as optional with the same sub-fields as v1
```

## Implementation note — testability and single-source-of-truth

`codebase-recon` is an LLM agent, but Step 6.5's enumeration is a mechanical shell pipeline. Per decision #1, that pipeline lives in exactly one shipped file: `plugins/agentic-dev-team/scripts/recon-inventory.sh`. The agent prompt instructs Claude to invoke the script. Tests invoke the same script (not a copy). Byte-identical determinism across agent runs and test runs follows by construction.

The excludes file (`plugins/agentic-dev-team/knowledge/recon-inventory-excludes.txt`) is the single source of truth for filesystem-walk exclusions. Script, contract doc, and rubric all read from or cross-reference this file.

## Steps

### Step 1: Add `file_inventory` to both schemas + consumer-contract fixture

**Complexity**: standard

**RED**:

- Create `evals/primitives-contract/fixtures/` if absent.
- Create `evals/primitives-contract/fixtures/recon-envelope-with-file-inventory.json` — positive case, envelope containing a well-formed `file_inventory` object. (Hand-authored from the spec's shape definition, not copied from any current output.)
- Create `evals/primitives-contract/fixtures/recon-envelope-file-inventory-malformed-source.json` — negative, `source: "unknown-tool"`.
- Create `evals/primitives-contract/fixtures/recon-envelope-file-inventory-partial.json` — negative, missing `count` and `sibling_ref`.
- Create `evals/primitives-contract/fixtures/file-inventory-consumer-contract.json` — a minimal contract-freeze fixture asserting the four required properties (for AC-12).
- Create `evals/primitives-contract/validate.sh` if absent — a thin wrapper around a JSON Schema validator (see R1).
- Create `evals/primitives-contract/tests/schema-file-inventory.sh` — runs `validate.sh` against each fixture and asserts expected pass/fail.
- Run the test. It fails because schemas don't define the field yet.

**GREEN**:

- Edit `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json`: add optional `file_inventory` object with sub-properties `source` (enum `["git-ls-files", "filesystem-walk"]`), `count` (integer ≥ 0), `sibling_ref` (string). All three `required` within the sub-object.
- Edit `evals/codebase-recon/expected-schema.json`: bump `schema_version` const to `"0.2"`; update title to `"v0.2 — placeholder"`; mirror the same optional `file_inventory` addition.
- Conformance tests pass.

**REFACTOR**: None.

**Files**:

- `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json`
- `evals/codebase-recon/expected-schema.json`
- `evals/primitives-contract/fixtures/*` (4 new)
- `evals/primitives-contract/validate.sh` (new if absent)
- `evals/primitives-contract/tests/schema-file-inventory.sh` (new)

**Commit**: `feat(recon): add optional file_inventory to envelope schemas (contract 1.2.0)`

### Step 2: Canonical enumeration script + excludes file + ts-monorepo genuine-RED fixture

**Complexity**: complex (sets up the single-source-of-truth scaffolding that the rest of the plan depends on)

**Ground-truth fixture listing** (authored here from `find` output, NOT from the pipeline under test):

```text
.env.example
.github/workflows/ci.yml
package.json
packages/api/package.json
packages/api/src/notify.ts
packages/api/src/routes/auth.ts
packages/api/src/server.ts
packages/core/package.json
packages/core/src/errors.ts
packages/core/src/index.ts
```

**RED**:

- Write `evals/codebase-recon/fixtures/ts-monorepo/expected-inventory.txt` with exactly the 10 lines above, sorted lexicographically under `LC_ALL=C`, LF-terminated, no trailing blank line. This is hand-authored from the fixture's ground truth + the sort/dedup rules in the spec.
- Write `evals/codebase-recon/fixtures/ts-monorepo/expected-file-inventory.json` with contents:

    ```json
    { "source": "git-ls-files", "count": 10, "sibling_ref": "recon-ts-monorepo.inventory.txt" }
    ```

- Create `plugins/agentic-dev-team/scripts/recon-inventory.sh` as an **empty stub** that exits 0 with no output. (This is the deliberate fail-first: a non-implementation so the test proves the diff fails for the right reason.)
- Create `plugins/agentic-dev-team/knowledge/recon-inventory-excludes.txt` with the exclude list from the spec (prefix section markers for `.git/`, `node_modules/`, `.venv/`, `__pycache__/`, `dist/`, `build/`, `target/`, `.tox/`, `.next/`, `.nuxt/`; filename section markers for `.DS_Store`, `Thumbs.db`). Ships with the plugin (per decision #2).
- Create `evals/codebase-recon/tests/inventory-ts-monorepo.sh`:
  - Sets up a scratch git repo in a tmpdir with the ts-monorepo fixture contents (copy fixture files, `git init`, `git add .`, `git commit`).
  - Invokes `plugins/agentic-dev-team/scripts/recon-inventory.sh <tmpdir> --emit-main-inventory-json <tmpfile>`.
  - Diffs script stdout vs `expected-inventory.txt`. Diffs tmpfile vs `expected-file-inventory.json`.
  - Asserts non-zero-count diff against the empty stub (proof of genuine RED).
- Run the test. Fails with a clear "expected 10 lines, got 0" signal. **Do not proceed until this failure is observed.**

**GREEN**:

- Implement the canonical script. Git branch: `git -C "$ROOT" ls-files -z | tr '\0' '\n' | LC_ALL=C sort -u`. Emit main-envelope JSON object to the file passed via `--emit-main-inventory-json` (or to stdout with `--json-only`, TBD at implementation time). Exit 0 on success.
- Run the test. Passes.

**REFACTOR**: None at this step — excludes file and canonical script are already at their canonical locations by design.

**Files**:

- `plugins/agentic-dev-team/scripts/recon-inventory.sh` (new)
- `plugins/agentic-dev-team/knowledge/recon-inventory-excludes.txt` (new)
- `evals/codebase-recon/fixtures/ts-monorepo/expected-inventory.txt` (new, hand-authored)
- `evals/codebase-recon/fixtures/ts-monorepo/expected-file-inventory.json` (new)
- `evals/codebase-recon/tests/inventory-ts-monorepo.sh` (new)

**Commit**: `feat(recon): canonical inventory enumeration script + ts-monorepo fixture`

### Step 3: Polyglot fixture — genuine-RED hand-authored

**Complexity**: trivial

**Ground-truth fixture listing**:

```text
backend/app.py
backend/requirements.txt
frontend/package.json
frontend/src/main.ts
scripts/deploy.sh
```

**RED**:

- Write `evals/codebase-recon/fixtures/polyglot/expected-inventory.txt` with those 5 lines, `LC_ALL=C`-sorted, LF-terminated.
- Write `evals/codebase-recon/fixtures/polyglot/expected-file-inventory.json` with `count: 5`, `sibling_ref: "recon-polyglot.inventory.txt"`, `source: "git-ls-files"`.
- Create `evals/codebase-recon/tests/inventory-polyglot.sh` mirroring the ts-monorepo test structure.
- Seed RED failure: temporarily rename the script to force a not-found (or revert it to the stub locally). Confirm the test fails.

**GREEN**: Restore the script. Test passes against the canonical pipeline already implemented in Step 2.

**REFACTOR**: None.

**Files**:

- `evals/codebase-recon/fixtures/polyglot/expected-inventory.txt` (new)
- `evals/codebase-recon/fixtures/polyglot/expected-file-inventory.json` (new)
- `evals/codebase-recon/tests/inventory-polyglot.sh` (new)

**Commit**: `test(recon): polyglot fixture inventory baseline`

### Step 4: Filesystem-walk branch + exclude-list consumption

**Complexity**: standard

**RED**:

- Create `evals/codebase-recon/fixtures/non-git-basic/` with a representative structure: regular kept files (e.g., `src/main.ts`, `README.md`, dotfile `.env.example`) plus exclude candidates (`.DS_Store`, `Thumbs.db`, `node_modules/pkg/index.js`, `.venv/lib/python3.11/site.py`, `dist/bundle.js`, `build/output.js`).
- Hand-author `expected-inventory.txt` listing ONLY the kept files, sorted.
- Hand-author `expected-file-inventory.json` with `source: "filesystem-walk"`.
- Create `evals/codebase-recon/tests/inventory-non-git.sh` — invokes `scripts/recon-inventory.sh <dir> --force-filesystem-walk --emit-main-inventory-json <tmp>` and diffs both outputs.
- Seed RED failure: test fails because script doesn't have a filesystem-walk branch yet.

**GREEN**:

- Extend `scripts/recon-inventory.sh` with the filesystem-walk branch: triggered when `.git/` absent or when `--force-filesystem-walk`. Reads `plugins/agentic-dev-team/knowledge/recon-inventory-excludes.txt`, parses the two sections (`# prefix:`, `# filename:`), uses `find` with `-not -path` for prefixes and `-not -name` for filenames, sorts `LC_ALL=C`, dedupes.
- Skip non-regular files (`find -type f`). Resolve symlinks; broken links recorded to stderr with a `# BROKEN_SYMLINK:` marker that the test harness can capture into envelope `notes`.
- Test passes.

**REFACTOR**: None — excludes file was canonical from Step 2.

**Files**:

- `plugins/agentic-dev-team/scripts/recon-inventory.sh` (updated)
- `evals/codebase-recon/fixtures/non-git-basic/**` (new)
- `evals/codebase-recon/tests/inventory-non-git.sh` (new)

**Commit**: `feat(recon): filesystem-walk branch with standard excludes`

### Step 5: Submodule + symlink edge cases

**Complexity**: complex

**RED**:

- Create `evals/codebase-recon/fixtures/submodule-symlink/` with a `setup.sh` script that initializes the fixture at test time (per R2 resolution: option b — setup script keeps the fixture committable without a nested `.git/`):
  - Creates regular files `src/handlers/auth.ts`, `src/index.ts`.
  - Creates a symlink `src/alias.ts -> src/handlers/auth.ts`.
  - Creates a broken symlink `src/orphan.ts -> does-not-exist.ts`.
  - Creates a submodule at `vendor/sub` using a tiny bare repo stub under `.stub/sub.git/`.
- Hand-author `expected-inventory.txt` listing `src/handlers/auth.ts` once (no `src/alias.ts`), `src/index.ts`, `vendor/sub` (gitlink entry), but NOT `src/orphan.ts`.
- Hand-author `expected-notes.txt` listing the expected broken-link observation captured from stderr.
- Hand-author `expected-file-inventory.json`.
- Create `evals/codebase-recon/tests/inventory-submodule-symlink.sh`. RED fails because script doesn't handle symlinks or capture broken-link notes.

**GREEN**:

- Harness: submodules need no special handling — `git ls-files` emits gitlink entries as single paths. Confirm with fixture.
- Symlink logic: after `git ls-files` emits paths, run a post-pass that reads each entry with `readlink -f`; if target is outside the repo root or doesn't exist, drop from inventory and emit `# BROKEN_SYMLINK: <src> -> <dst>` to stderr; otherwise substitute the resolved relative path, then re-sort + dedupe.
- Non-git branch: `find -type f` doesn't follow symlinks by default; add the same post-pass.
- Test passes.

**REFACTOR**: If git and non-git branches end up with the same symlink-resolution block, extract a `_resolve_symlinks()` shell function.

**Files**:

- `plugins/agentic-dev-team/scripts/recon-inventory.sh` (updated)
- `evals/codebase-recon/fixtures/submodule-symlink/**` (new)
- `evals/codebase-recon/tests/inventory-submodule-symlink.sh` (new)

**Commit**: `feat(recon): submodule + symlink handling in inventory`

### Step 6: Agent procedure + contract doc + consumer error contract + rubric + pipeline budget

**Complexity**: standard

**RED**:

- Create `evals/primitives-contract/fixtures/recon-envelope-pre-1.2.0.json` — valid pre-1.2.0 envelope without `file_inventory`.
- Create `evals/primitives-contract/tests/backward-compat-1.2.0.sh`:
  - Asserts pre-1.2.0 envelope still schema-validates against 1.2.0 schema (AC-10).
  - Invokes a consumer stub `evals/primitives-contract/fixtures/consumer-stub-fail-open.sh` against the pre-1.2.0 envelope; asserts stub emits the documented one-time notice to stderr and exits 0 (AC-10a).
  - Invokes the stub against an envelope whose declared `count` mismatches sibling `wc -l`; asserts same fail-open branch (AC-13 branch b).
  - Invokes the stub against an envelope whose declared sibling file is absent; asserts same fail-open branch (AC-13 branch a).
- Create doc-semantic tests (not plain grep) using `awk`:
  - `evals/primitives-contract/tests/contract-1.2.0-doc.sh`: asserts the literal header line `version: 1.2.0`, asserts `### 1.2.0 (YYYY-MM-DD)` Changelog entry exists, asserts the string `file_inventory` appears under a `## Envelope 1` heading (not merely anywhere), asserts a `### Consumer error contract` subsection exists under Envelope 1.
  - `evals/codebase-recon/tests/agent-has-step-6-5.sh`: asserts Step 6.5 heading exists, asserts the agent prompt invokes `scripts/recon-inventory.sh` by path, asserts the handoff-contract section mentions `file_inventory.sibling_ref`.
  - `evals/codebase-recon/tests/rubric-inventory.sh`: asserts rubric names both inventory-determinism and sibling-contract-compliance criteria by their headings.
- Create pipeline budget test `evals/codebase-recon/tests/inventory-budget.sh`:
  - Runs `scripts/recon-inventory.sh` against the polyglot fixture 5 times.
  - Asserts p95 (4th-highest of 5) is under 200 ms. Configurable budget in an env var if CI needs headroom.
  - Closes AC-11.
- All RED tests fail against the current tree.

**GREEN**:

- Update `plugins/agentic-dev-team/knowledge/security-primitives-contract.md`:
  - Bump header version to `1.2.0`.
  - In "Envelope 1 — RECON" subsection, document `file_inventory` object: shape, sibling-file contract, `source` enum semantics, why externalized (cross-reference `scripts/recon-inventory.sh`).
  - Add new subsection `### Consumer error contract` under Envelope 1 covering the three fail-open branches (field absent, sibling absent, count mismatch) with exact stderr notice templates.
  - Add Changelog entry `### 1.2.0 (2026-04-24)` describing the additive change and `^1.0.0` consumer compatibility guarantee.
- Update `plugins/agentic-dev-team/agents/codebase-recon.md`:
  - Insert **Step 6.5: Enumerate inventory** between Step 6 (git-history probe) and Step 7 (emit). The step instructs: run `plugins/agentic-dev-team/scripts/recon-inventory.sh <repo-root> --emit-main-inventory-json <main-envelope-fragment>`. Capture stderr for broken-link notes (feed into envelope `notes`). Write sibling file to `memory/recon-<slug>.inventory.txt`.
  - Update Step 7 emit block to list `memory/recon-<slug>.inventory.txt` as an artifact and print the full relative path + line count in the dispatcher summary (UX discoverability warning from review).
  - Update "Handoff contract" to note future consumers can rely on `file_inventory.sibling_ref` and must follow the documented fail-open path if any of the three branches fires.
- Update `evals/codebase-recon/rubric.md`: add `### Inventory determinism` and `### Sibling-file contract compliance` criteria, each pointing to the authoritative test.
- Create `evals/primitives-contract/fixtures/consumer-stub-fail-open.sh`: 30-line shell that loads an envelope, tries to find the inventory, hits each of the three failure branches, emits the documented stderr notice, exits 0. Used only for fail-open verification.
- Run all Step-6 tests. Pass.

**REFACTOR**: If the sibling-file contract prose in the contract doc and the agent doc duplicate, keep authoritative statement in the contract doc and have the agent doc cross-reference.

**Files**:

- `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` (updated)
- `plugins/agentic-dev-team/agents/codebase-recon.md` (updated)
- `evals/codebase-recon/rubric.md` (updated)
- `evals/primitives-contract/fixtures/recon-envelope-pre-1.2.0.json` (new)
- `evals/primitives-contract/fixtures/consumer-stub-fail-open.sh` (new)
- `evals/primitives-contract/tests/backward-compat-1.2.0.sh` (new)
- `evals/primitives-contract/tests/contract-1.2.0-doc.sh` (new)
- `evals/codebase-recon/tests/agent-has-step-6-5.sh` (new)
- `evals/codebase-recon/tests/rubric-inventory.sh` (new)
- `evals/codebase-recon/tests/inventory-budget.sh` (new)

**Commit**: `docs(recon): contract 1.2.0 + codebase-recon Step 6.5 + fail-open consumer contract + pipeline budget`

## Complexity Classification

| Step | Rating   | Rationale |
| ---- | -------- | --------- |
| 1    | standard | Schema edits + conformance fixtures |
| 2    | complex  | Sets up the single-source-of-truth scaffolding; genuine-RED against empty stub |
| 3    | trivial  | Pure fixture-baseline addition; no code change |
| 4    | standard | Extends harness with filesystem-walk branch + excludes consumption |
| 5    | complex  | Symlink + submodule handling is the failure-prone edge |
| 6    | standard | Cross-file doc updates + fail-open consumer contract + pipeline budget |

## Pre-PR Quality Gate

- [ ] All `evals/codebase-recon/tests/*.sh` and `evals/primitives-contract/tests/*.sh` pass
- [ ] JSON Schema validation on both schemas (via `evals/primitives-contract/validate.sh`)
- [ ] Pipeline budget test passes p95 < 200 ms on the polyglot fixture
- [ ] Observational 10k-repo time-to-emit captured and attached to PR description
- [ ] `/code-review` passes on the diff
- [ ] Manual verification: run `codebase-recon` against a real target repo; inspect the sibling file; confirm dispatcher summary renders
- [ ] `security-primitives-contract.md` header version matches the Changelog top-entry version

## Risks & Open Questions

| #   | Type                  | Item | Mitigation / Owner |
| --- | --------------------- | ---- | ------------------ |
| R1  | Risk                  | JSON Schema validator CLI availability. No current `validate.sh` on the repo tree. | Step 1 RED creates `evals/primitives-contract/validate.sh`. First choice: `python -m jsonschema` (stdlib-adjacent, low friction). Fallback: `ajv-cli` via `npx`. Pick during Step 1. |
| R2  | Risk                  | Submodule fixture (Step 5). Resolved — use a `setup.sh` creating the submodule at test time from a tiny bare-repo stub. | Baked into Step 5 RED. |
| R3  | Open                  | 10k-repo performance (AC-11 spec language) is not CI-asserted. Re-scoped in this plan to a pipeline-only budget on polyglot; 10k-repo number becomes observational on PR. | Accepted in decision #4. User may require a CI-asserted 10k number — say now if so and I'll add a synthetic-10k-file generator step. |
| R4  | Open                  | Case normalization deferred to Gap 6 per spec. | No action here. |
| R5  | Resolved              | Canonical pipeline location. | Decision #1 above. |
| R6  | Open                  | Contract 1.2.0 triggers release-please minor bump on `agentic-dev-team`. Confirm `plugin.json` + release-please config before Step 6 commit lands on main. | Check during Step 6 GREEN. |
| R7  | Resolved              | `evals/primitives-contract/{fixtures,tests}/` directory existence — Step 1 RED creates if absent. | Baked into Step 1. |
| R8  | Open                  | Spec amendment. Three scenarios added at plan level (empty repo, consumer fail-open on missing sibling, consumer fail-open on count mismatch) are plan-level tests; the spec should be amended in a follow-up to keep the two aligned. | File a separate spec-amendment commit or bundle with the implementation PR. |
| R9  | Open (strategic)      | The whole slice may be avoidable. Strategic critic recommended spiking Gap 6 first against the union of existing RECON path fields (`entry_points`, `security_surface.*`, layer paths) without any contract bump. If warn-only FP rate proves acceptable, 6a can be scrapped. | User call — see summary below. Plan as written assumes 6a ships. |
| R10 | Open (UX)             | `sibling_ref` naming — the reviewer flagged that a bare basename is a thin breadcrumb; `sibling_path` with the full `memory/recon-<slug>.inventory.txt` path is clearer. Would be a spec change. | Non-blocker. Raise to user in the summary; default to keeping `sibling_ref` as specified unless user says otherwise. |

## Plan Review Summary

Four personas ran in parallel against v1. All returned `needs-revision`. v2 resolves all six blockers. Warnings and observations are surfaced below for user awareness. Three reviewers re-ran against v2 and all returned `approve`.

### Blockers resolved in v2

| Reviewer | Blocker | Resolution |
| -------- | ------- | ---------- |
| Acceptance Test Critic | AC-11 unfalsifiable (observational only) | Re-scoped AC-11 to pipeline-only budget on polyglot fixture (<200 ms p95); 10k-repo becomes observational PR attachment |
| Acceptance Test Critic | AC-10 dropped fail-open consumer behavior from spec | New AC-10a + AC-13 + `consumer-stub-fail-open.sh` + backward-compat test branches for all three fail-open cases |
| Acceptance Test Critic | Rubber-stamp RED in Steps 2/3 (expected harvested from SUT) | Steps 2/3 now hand-author expected-inventory.txt from enumerated fixture ground truth; Step 2 uses an empty-stub script to prove genuine RED fails for the right reason |
| Design & Architecture Critic | Two competing sources of truth for enumeration pipeline | Decision #1 locks canonical script at `plugins/agentic-dev-team/scripts/recon-inventory.sh` |
| Design & Architecture Critic | Plugin reaching into `evals/` for runtime code | Canonical script ships with the plugin; `evals/` harness invokes it; no runtime dependency on test tree |
| UX Critic | Consumer error contract missing for sibling-absent / count-mismatch / field-absent | Decision #3 + new `### Consumer error contract` subsection in contract doc + Step 6 tests |

### Warnings surfaced (not addressed — user discretion)

- **Strategic — R9:** The whole slice may be avoidable. Recommendation: spike Gap 6's hook first against a union of existing RECON path fields. If FP rate is acceptable, scrap 6a. Current plan assumes 6a ships.
- **Strategic:** Opportunity cost — Gaps 1 (concurrency) and 2 (git-history secrets) close detection holes with direct user value; 6a services the lowest-leverage gap with the most formal work.
- **Strategic:** MINOR bump on a cross-plugin envelope rarely truly additive. De-facto-required field emerges when consumers start assuming presence. Current plan keeps field optional at schema and documents fail-open — mitigates but doesn't eliminate.
- **Strategic:** Steps 3–5 could be deferred to 1.3.0 if scope reduction is desired. Minimum viable subset = Steps 1, 2, 6 only.
- **Design:** Sibling-file-plus-JSON-pointer pattern is newly invented; no generalization into a reusable `external_ref` sub-schema. Future large fields may reinvent inconsistently.
- **Design:** Spec colocation in `agentic-security-assessment/docs/specs/` inverts envelope ownership. Consider cross-reference from `agentic-dev-team`.
- **UX — R10:** Rename `sibling_ref` → `sibling_path` with full relative path. Would be a spec change; flagged for user.
- **UX:** Enum values `git-ls-files` / `filesystem-walk` mix tool name with activity. Alternatives: `git` / `filesystem`. Observation-level; defer.
- **Acceptance:** Missing scenarios — symlink cycles, directory symlinks, non-UTF-8 filenames, atomic-write. Not blockers; would strengthen the test suite if added later.

### Observations

- Testability via shell pipeline (not LLM) is the right contract (all reviewers agreed).
- MINOR contract bump is correctly classified per the versioning lifecycle.
- Explicit out-of-scope list in the spec is disciplined.
- Backward-compat fixture protects consumers.
