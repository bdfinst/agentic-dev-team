# Spec: RECON envelope `file_inventory`

> Precondition for Gap 6 (forbid LLM tree re-walks). Separable, independently shippable.
>
> **Source prompt:** `.prompts/close-gaps-vs-opus-repo-scan.md` Gap 6 (acceptance requires a RECON manifest to check reads against; the current envelope has no authoritative file list).
>
> **Cross-plugin:** This slice modifies `plugins/agentic-dev-team/` (envelope owner). Spec colocated here with Gap 6 for trail continuity.

## Intent Description

The RECON envelope today has no authoritative list of files the recon considered part of the target repo. Structured fields (`entry_points`, `security_surface.*`, layer paths, `sensitive_file_history`) partially overlap with source files but are not a complete inventory — a legitimate source file that isn't referenced in any structured field is undiscoverable from the envelope. Gap 6's manifest-membership hook requires that authoritative list.

Extend the RECON envelope (primitives contract 1.2.0, MINOR bump) with a `file_inventory` field: a deterministic enumeration of every file the target repo contains at recon time. Because mid-size repos have tens of thousands of files and embedding that into the main JSON bloats diffs and validation cost, the inventory ships as a **sibling file** (`memory/recon-<slug>.inventory.txt`, one repo-relative path per line) with a pointer and count in the main envelope.

The field is optional at schema level so consumers declaring `required-primitives-contract: ^1.0.0` aren't broken, but `codebase-recon` always emits it from 1.2.0 forward.

Scope applies to all 10 LLM agents in `agentic-security-review` that will consume the inventory via Gap 6's hook: `fp-reduction`, `business-logic-domain-review`, `cross-repo-synthesizer`, `exec-report-generator`, `tool-finding-narrative-annotator`, `compliance-edge-annotator`, `redteam-recon-analyzer`, `redteam-evasion-analyzer`, `redteam-extraction-analyzer`, `redteam-report-generator`.

## User-Facing Behavior

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
    And the walk excludes prefixes: .git/ node_modules/ .venv/ __pycache__/ dist/ build/ target/ .tox/ .next/ .nuxt/
    And the walk excludes filenames: .DS_Store, Thumbs.db
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
    And a consumer reading file_inventory observes it is absent
    And the consumer's documented behavior is to fail-open with a one-time staleness notice

  Scenario: Contract version bump
    Then plugins/agentic-dev-team/knowledge/security-primitives-contract.md declares version 1.2.0
    And the Changelog section documents the addition
    And consumers declaring required-primitives-contract: ^1.0.0 install unmodified

  Scenario: v0.1 placeholder schema mirrors the addition
    Then evals/codebase-recon/expected-schema.json bumps schema_version const to "0.2"
    And file_inventory is added as optional with the same sub-fields as v1

  Scenario: Eval fixtures carry expected-inventory artifacts
    Given fixtures evals/codebase-recon/fixtures/ts-monorepo and .../polyglot
    Then each fixture has an expected-inventory.txt alongside
    And each fixture has an expected-file-inventory.json giving the main-envelope file_inventory object
    And running codebase-recon on the fixture produces byte-identical inventory plus matching envelope sub-object
```

## Architecture Specification

### Components affected

| Component | Change |
|---|---|
| `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` | Bump header version to 1.2.0; add `file_inventory` subsection under Envelope 1; Changelog entry |
| `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json` | Add optional `file_inventory` object `{ source, count, sibling_ref }` |
| `evals/codebase-recon/expected-schema.json` | Bump `schema_version` const to `"0.2"`; mirror the `file_inventory` addition as optional |
| `plugins/agentic-dev-team/agents/codebase-recon.md` | Insert Step 6.5 "Enumerate inventory" between git-history probe and artifact emission; update Step 7 to write the sibling file |
| `evals/codebase-recon/fixtures/ts-monorepo/expected-inventory.txt` | New — deterministic expected inventory |
| `evals/codebase-recon/fixtures/ts-monorepo/expected-file-inventory.json` | New — expected main-envelope `file_inventory` object |
| `evals/codebase-recon/fixtures/polyglot/expected-inventory.txt` | New |
| `evals/codebase-recon/fixtures/polyglot/expected-file-inventory.json` | New |
| `evals/codebase-recon/rubric.md` | Add inventory-determinism + sibling-file-contract criteria |

### JSON shape (main envelope)

```json
"file_inventory": {
  "source": "git-ls-files" | "filesystem-walk",
  "count": <integer>,
  "sibling_ref": "recon-<slug>.inventory.txt"
}
```

All four sub-fields required when the object is present. Object itself is optional at schema level (backward compat).

### Sibling file contract

- Path: `memory/recon-<slug>.inventory.txt`
- UTF-8, LF line terminators, no BOM
- One repo-relative path per line, final line newline-terminated
- Sorted lexicographically under `LC_ALL=C` for cross-locale determinism
- Deduplicated
- Path separator `/` on every platform
- No leading `./`
- No symlink entries (resolved to real paths; broken symlinks skipped)
- No entries for excluded prefixes / filenames (non-git branch)
- Plain text — not JSON, not validated by schema tooling

### Enumeration algorithm

**Git branch** (`.git/` exists at repo root):

```
git -C <root> ls-files -z | split on NUL | LC_ALL=C sort -u
```

Submodule gitlinks appear once (default git ls-files behavior). No recursive descent.

**Non-git branch**:

Depth-first walk rooted at `<root>`, with:

- Prune prefixes: `.git/`, `node_modules/`, `.venv/`, `__pycache__/`, `dist/`, `build/`, `target/`, `.tox/`, `.next/`, `.nuxt/`
- Skip filenames: `.DS_Store`, `Thumbs.db`
- Skip non-regular files (devices, fifos, sockets)
- Resolve symlinks; include only the real-path target; record broken links to the envelope's `notes` array
- Sort (`LC_ALL=C`), deduplicate

### Versioning & compatibility

- Additive optional field → MINOR bump (contract 1.1.0 → 1.2.0).
- Consumers on `^1.0.0` continue to install unchanged.
- `codebase-recon` always emits the field from 1.2.0 forward — de facto required behaviorally, optional at schema level.
- Pre-1.2.0 envelopes in `memory/` remain schema-valid; consumers that need the field (Gap 6's hook) fail-open with a one-time staleness notice when absent.

### Performance constraint

Time-to-emit must not regress >500 ms on a 10 000-file repo versus pre-1.2.0 baseline. Sort and dedup are the hot path; use the shell pipeline above rather than reimplementing in agent prompt logic.

### Case normalization

Inventory preserves verbatim path case as returned by `git ls-files` or the filesystem walk. Case normalization is Gap 6's hook's concern (it will lowercase both sides before comparing to handle case-insensitive filesystems on macOS / Windows).

### Out of scope

- The membership check itself (Gap 6 — separate spec)
- Per-file metadata (size, mtime, classification)
- Delta / change detection vs a prior recon
- Inventory for paths outside the repo root
- Case normalization at the inventory level
- Inventory size cap (no cap — repos of any size are supported; performance budget is the only guardrail)

## Acceptance Criteria

| # | Criterion | Pass |
|---|---|---|
| AC-1 | Primitives contract bumped | `security-primitives-contract.md` header shows version 1.2.0 and a Changelog entry documents the `file_inventory` addition |
| AC-2 | v1 schema updated | `recon-envelope-v1.json` declares optional `file_inventory` object with `source`, `count`, `sibling_ref` |
| AC-3 | v0.1 placeholder mirrored | `evals/codebase-recon/expected-schema.json` bumps `schema_version` const to `"0.2"` and adds the optional `file_inventory` object |
| AC-4 | Sibling file emitted on git target | On a git target, `memory/recon-<slug>.inventory.txt` exists; sorted; deduped; LF-terminated; no blank lines |
| AC-5 | Main envelope references sibling | `file_inventory.count` equals `wc -l` of the sibling; `sibling_ref` matches the sibling's basename |
| AC-6 | Non-git fallback | On a non-git target, the walk excludes the full prefix and filename list and produces a valid inventory |
| AC-7 | Submodule handling | Submodule gitlink appears once; no recursive descent verified by a fixture that includes a submodule |
| AC-8 | Symlink handling | Only real-path targets appear; no double-count; broken links captured in `notes` |
| AC-9 | Fixture expected outputs | `ts-monorepo` and `polyglot` fixtures each ship `expected-inventory.txt` + `expected-file-inventory.json`; regenerating matches byte-for-byte |
| AC-10 | Backward compatibility | A pre-1.2.0 envelope (sample committed under `evals/codebase-recon/fixtures/`) still validates against the 1.2.0 schema |
| AC-11 | Performance | `codebase-recon` time-to-emit regresses by less than 500 ms on a 10 000-file repo vs baseline |
| AC-12 | Gap 6 unblocked | Field shape is final and stable; Gap 6's hook spec can reference `file_inventory.sibling_ref` without further negotiation |

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior has a corresponding BDD scenario
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts

**Gate: PASS (2026-04-24).** Proceeding to `/plan`.
