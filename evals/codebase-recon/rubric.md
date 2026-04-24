# codebase-recon eval rubric

Grading criteria for `codebase-recon` agent output against the fixtures in `evals/codebase-recon/fixtures/`. Each fixture's RECON artifact is compared against this rubric plus the JSON Schema at `evals/codebase-recon/expected-schema.json`.

## Hard gates (must-pass; any failure = fixture fails)

1. **Schema conformance**: The emitted `memory/recon-<slug>.json` validates against `expected-schema.json` without warnings.
2. **File written to memory/**: Both `.md` (human-readable) and `.json` (machine-readable) artifacts present at the expected path.
3. **Git history section present**: `git_history.branches`, `git_history.recent_activity`, `git_history.sensitive_file_history` all populated (may be empty arrays but keys must exist).
4. **Timestamps valid**: `generated_at` is a valid ISO-8601 UTC datetime within 5 minutes of the eval run.

### Inventory determinism

The sibling file `memory/recon-<slug>.inventory.txt` must be byte-identical across repeated recon runs on the same input. The authoritative test: `evals/codebase-recon/tests/inventory-ts-monorepo.sh` + `inventory-polyglot.sh`. Hard gate — any non-determinism fails the fixture.

### Sibling-file contract compliance

The sibling file and the main-envelope `file_inventory` object must agree on every structural rule from `knowledge/security-primitives-contract.md#file_inventory-added-in-120` and `#consumer-error-contract`:

- Sibling is LF-terminated, `LC_ALL=C` sorted, deduplicated, no blank lines
- `file_inventory.count == wc -l <sibling>`
- `file_inventory.sibling_ref` matches the basename of the emitted sibling
- `file_inventory.source` is the enum value actually used by the canonical script

Authoritative tests: `evals/codebase-recon/tests/inventory-*.sh` (ts-monorepo, polyglot, non-git-basic, submodule-symlink) and `evals/primitives-contract/tests/backward-compat-1.2.0.sh`. Hard gate — any mismatch fails the fixture.

## Fixture-specific correctness

### ts-monorepo fixture

- `repo.monorepo` is `true`.
- `repo.workspaces` contains `packages/core` and `packages/api` (exact strings).
- `repo.package_manager` is `npm` (detected from `package.json` in the ts-monorepo root).
- `entry_points` includes:
  - `packages/api/src/server.ts` classified as `http-server` (has `app.listen` pattern)
  - `packages/core/src/index.ts` classified as `module-index` (library entry, re-exports)
- `languages[0].name` is `TypeScript`.
- `security_surface.auth_paths` includes `packages/api/src/routes/auth.ts`.
- `security_surface.network_egress` includes at least one path referencing outbound HTTP.
- `git_history.sensitive_file_history` detects `.env.example` (should be `in_current_tree: true`).

### polyglot fixture

- `repo.monorepo` is `false`.
- `repo.package_manager` is one of `mixed` or the dominant value for the fixture (`npm` OR `pip` — both are reasonable since this fixture ships both).
- `entry_points` includes:
  - `backend/app.py` classified as `http-server` (FastAPI style decorator pattern)
  - `frontend/src/main.ts` classified as `module-index` or `http-server` (both acceptable depending on inference)
  - `scripts/deploy.sh` classified as `cli` (has `#!/usr/bin/env bash` shebang and entry behavior)
- `languages` contains at least `Python`, `TypeScript`, `Shell` — ranking is by file count and may vary.
- `security_surface.crypto_calls` includes `backend/app.py` (which imports/uses a crypto primitive — seed the fixture accordingly).
- `security_surface.ml_models_loaded` is either empty array or references the `backend/` if ML loading pattern is seeded.

## Narrative quality (soft — scored 0-3 per item)

1. **Architecture summary**: 2-4 sentences. Must identify layer structure (e.g. "core/api separation" or "backend/frontend split"). Score 3 if the summary would let a reader locate domain logic without browsing. Score 1 if it's a file listing in prose.
2. **Entry-point rationale**: Each entry point's `rationale` field cites a concrete signal (shebang, framework decorator, package.json `main`, server-binding call). Score 3 if all rationales are specific; score 1 if any are vague ("looks like an entry point").
3. **Notes section**: Non-empty when the repo has non-obvious structure; empty when structure is conventional. Not scored if empty for conventional repos.

## Grading aggregation

- All hard gates pass → fixture passes.
- Fixture-specific correctness: ≥ 90% of listed assertions pass → pass; 75-89% → warn; < 75% → fail.
- Narrative quality: aggregate score averaged across items; ≥ 2.0 → pass; 1.0-1.99 → warn; < 1.0 → fail.

A fixture's overall verdict is the worst of the three axes.

## Rubric evolution

This rubric is v0.1. Expected changes as the agent matures:

- When P2 Step 4 lands, the schema version moves from 0.1 → 1.0 (primitives contract). Update the schema field reference.
- Add fixtures for: Go backends, Rust libraries, mixed Terraform+app repos.
- Tighten narrative quality to a 5-point scale with worked examples.
