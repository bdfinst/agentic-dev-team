<!-- spec-version: 1 -->
# Spec: `/plan` persists Gherkin to `.feature` files when the target project has a BDD convention

**Format:** dev-team specs v1
**Issue:** <https://github.com/bdfinst/agentic-dev-team/issues/537>

## Intent Description

`/plan` authors per-slice Gherkin scenarios inside the plan markdown — they are the behavioral contract every TDD step traces to. Today those scenarios die in the plan file: once the plan is archived to `plans/`, no BDD runner discovers them, no CI job asserts them, and no test-design tool can rediscover them. For a target project that already follows a BDD convention (existing `.feature` files, or a BDD runner dependency in its build manifest), the natural expectation is that `/plan`'s Gherkin also lands in the project's canonical features directory as `.feature` files.

This change makes `/plan` detect the target project's BDD convention at plan-creation time and, **after the plan is approved**, write each slice's Gherkin block to `<detected-dir>/<plan-slug>/slice-<N>-<slice-slug>.feature` — byte-for-byte identical to the inline block in the plan (modulo a single trailing newline), with no added header. The plan file remains the sole authoring surface; the `.feature` files are derived, write-once-per-plan-run artifacts. When no convention is detectable, an interactive run prompts the operator once (persist to `features/` / plan-file only / custom path); a non-interactive run defaults to plan-file-only without blocking. The decision is recorded in the plan file's metadata so re-runs of `/plan` on the same plan honor it without re-prompting.

Persist-only, by design: no step-definition stubs, no runner wiring, no CI integration, no bidirectional sync, and no retroactive generation for existing plans — those are explicitly out of scope (see issue #537's out-of-scope list). Detection is conservative: a false positive that writes `.feature` files into the wrong directory is worse than a false negative that merely prompts.

## Architecture Specification

**Components touched (5):**

1. **`plugins/dev-team/scripts/detect_bdd_convention.py`** (new, Python 3.8+ stdlib-only per ADR 0014). Deterministic detection of the target project's BDD convention, invoked by `/plan` the same way it already shells to `plan_waves.py` and `git_origin_host.py`. Emits JSON: `{"signal": "feature-files" | "manifest" | "none", "framework": <name or null>, "dir": <repo-relative destination or null>}`.
   - **Precedence: existing `.feature` files > BDD dependency in a manifest > no signal.**
   - `.feature` scan: the common directory of existing `.feature` files, excluding vendored/generated trees (`node_modules/`, `.git/`, `vendor/`, `dist/`, `build/`, virtualenvs). If `.feature` files live under **multiple unrelated roots**, report `none` (conservative — prompt rather than guess).
   - Manifest signals → canonical dirs (layouts per `knowledge/test-stack-profiles/bdd-frameworks.md`):
     | Signal | Manifest | Destination |
     |---|---|---|
     | `@cucumber/cucumber` / `cucumber-js` | `package.json` (devDependencies/dependencies) | `features/` |
     | `pytest-bdd` / `behave` | `pyproject.toml`, `requirements*.txt` | `features/` |
     | `Reqnroll` / `SpecFlow` | `*.csproj` | `Features/` under that test project's directory |
     | `io.cucumber` | `pom.xml`, `build.gradle`, `build.gradle.kts` | `src/test/resources/features/` |
     | `godog` | `go.mod` | `features/` |
   - If multiple manifests yield **conflicting** destinations, report `none`; multiple manifests sharing one destination are not a conflict. The same rule covers one framework with multiple candidate directories (e.g. two Reqnroll test csprojs) → `none`. Reqnroll's destination is pinned to `<csproj-directory>/Features` (repo-relative).
2. **`plugins/dev-team/scripts/plan_gherkin_export.py`** (new, Python 3.8+ stdlib-only). Deterministic exporter `/plan` shells to post-approval — the byte-for-byte copy is unit-tested code, not LLM prose (plan-review finding). Reads the plan file's `**Gherkin persistence**:` metadata line and each `### Slice N:` section's fenced Gherkin block (reusing/extending `scripts/lib/plan_parse.py`), writes `<dir>/<plan-slug>/slice-<N>-<slice-slug>.feature` (plan-slug = plan filename stem verbatim; slice-slug = slice title lowercased, non-alphanumeric runs collapsed to single hyphens, trimmed), and reports what it did: files written, files overwritten, stale derived files removed (the tool-owned dir is cleared of `*.feature` before writing — never silent), or a no-op note for plan-file-only/missing decisions (exit 0). Write failures (destination collides with a non-directory, unreadable plan) exit non-zero naming the offending path. The `<dir>/<plan-slug>/` subdirectory is tool-owned: anything inside is treated as derived and overwritable; files outside it are never touched.
3. **`plugins/dev-team/skills/plan/SKILL.md`** — two insertion points:
   - **Plan creation (step 2/3):** before any prompt logic, if a plan file already exists at the resolved output path and records a `**Gherkin persistence**:` decision, honor it — no re-detection, no re-prompt (editing that metadata line is the documented way to change the decision). Otherwise run the detection script; a non-zero detection exit is treated as no-signal with its stderr surfaced — planning never dies on it. Detected signal → use its destination. No signal + interactive → prompt the operator once: *"Persist Gherkin as .feature files? [y = features/<plan-slug>/ | n = plan file only | c = custom path]"*; a `c` path is validated (repo-relative, not under a vendored tree) and re-prompted with the rejection reason if invalid. No signal + non-interactive (`--yes`, `DEV_TEAM_AUTO_APPROVE=1`, or no TTY — the same triad step 6 already uses) → plan-file-only, with a logged skip line (*"skipping the Gherkin persistence prompt (non-interactive) — plan file only"*); never block. Record the resolved decision in the plan file's metadata block and echo it in the run output.
   - **Post-approval (step 6):** if the recorded decision is a persistence destination, shell to `plan_gherkin_export.py` and show its summary (files written/overwritten, destination) to the operator; surface a non-zero exit as a failure — never claim success on a failed export. This is a narrow, explicit carve-out to orchestrator constraint #1 ("no file edits beyond the plan file itself"): derived `.feature` writes happen only after the plan is approved and only via the export script, so unapproved scenarios never land in the working tree and review-persona revisions never leave stale files.
4. **`plugins/dev-team/skills/plan/references/plan-template.md`** — add a `**Gherkin persistence**: <destination dir | plan-file-only | custom: <path>>` line to the plan metadata block (alongside `**Created**` / `**Branch**` / `**Status**`), the machine-readable record re-runs honor.
5. **Tests** — pytest only (no `.bats`):
   - `tests/scripts/test_detect_bdd_convention.py` — fixture trees per stack exercising precedence, canonical-dir mapping, conflict → `none`, vendored-dir exclusion, and a sync-guard that the script's mapping table matches `bdd-frameworks.md` (drift guard).
   - `tests/scripts/test_plan_gherkin_export.py` — fixture plans exercising byte-for-byte export, overwrite reporting, no-op modes, and failure paths.
   - Content-guard assertions (extend the existing plan-skill guard suite under `tests/skills/` / `tests/repo/`) that `plan/SKILL.md` and `plan-template.md` carry the detection step, the prompt wording and validation, the non-interactive skip, the detection-failure fallback, the post-approval export instruction, and the metadata line.

**Behavior preserved / explicit non-changes:**

- The inline Gherkin block in the plan file is unchanged and remains the authoring surface; `.feature` files are derived copies.
- `gherkin-derive` is untouched — it derives scenarios *from code* (with provenance headers); this feature persists scenarios *from the plan* (verbatim, no header). They share only the canonical-layout knowledge in `bdd-frameworks.md`.
- `/build`, `/continue`, `progress-guardian`, and `plan_waves.py` are unaffected: the derived files exist before `/build` starts and nothing downstream parses them.
- `/ship` inherits the behavior via `/plan`; no `/ship` change.
- **Out of scope** (issue #537): executable BDD integration (stubs, runner wiring, CI), bidirectional sync (plan file is the source of truth; derived files are regenerated only by `/plan` runs), retroactive `.feature` generation for existing plans on `main`.

## Acceptance Criteria

Each criterion is a deterministic, observable pass/fail check.

**A1 — Feature-file signal beats manifest signal.** A fixture project containing both `.feature` files under `e2e/features/` and `@cucumber/cucumber` in `package.json`: `detect_bdd_convention.py` reports `signal: "feature-files"`, `dir: "e2e/features"`. Asserted by a pytest in `tests/scripts/test_detect_bdd_convention.py`.

**A2 — Each manifest signal maps to its canonical directory.** One fixture per stack (cucumber-js, pytest-bdd/behave, Reqnroll, cucumber-jvm Maven + Gradle, godog) with the dependency declared and no `.feature` files: the script reports `signal: "manifest"` and the destination from the table above. Asserted per-stack by pytest.

**A3 — Conservative on ambiguity.** (a) `.feature` files under two unrelated roots → `signal: "none"`. (b) Conflicting manifest destinations in one repo → `signal: "none"`. (c) `.feature` files only under `node_modules/` (or other vendored trees) → `signal: "none"`. Asserted by pytest.

**A4 — No-signal fixture yields no signal.** A fixture with no `.feature` files and no BDD dependency → `signal: "none"`, `dir: null`. Asserted by pytest.

**A5 — Operator prompt drives persistence when no signal.** `plan/SKILL.md` instructs: interactive no-signal runs prompt once with the accurate hint `[y = features/<plan-slug>/ | n = plan file only | c = custom path]`; `y` → `features/<plan-slug>/`, `n` → plan-file-only (no `.feature` files written), `c` → the operator-supplied path, validated (repo-relative, not vendored) with a re-prompt on invalid input; the recorded decision is echoed. Asserted by content-guard pytest on the skill text.

**A6 — Non-interactive runs never block on the persistence prompt.** `plan/SKILL.md` instructs: when non-interactive (same `--yes` / `DEV_TEAM_AUTO_APPROVE=1` / no-TTY triad as the approval gate) and no signal is detected, skip the prompt, default to plan-file-only, and log the skip. Asserted by content-guard pytest.

**A7 — Derived file content is byte-for-byte.** Each written `.feature` file's content equals the corresponding slice's inline Gherkin block exactly, modulo a single trailing newline — no added header, comment, or annotation. Asserted deterministically by `plan_gherkin_export.py`'s unit tests; `plan/SKILL.md` shells to the script rather than hand-copying.

**A8 — Writes happen only post-approval.** `plan/SKILL.md` places the export invocation after the step-6 approval gate and states the constraint-#1 carve-out (post-approval, via the export script only); no derived file is written while the plan status is `draft`. Asserted by content-guard pytest on step ordering in the skill text.

**A9 — Decision recorded and honored on re-run.** `plan-template.md`'s metadata block contains the `**Gherkin persistence**:` line; `plan/SKILL.md` instructs re-runs to read that line from an existing plan file at the resolved output path before any prompt logic and honor it without re-prompting, and names editing the line as the supported way to change the decision. Asserted by content-guard pytest on both files.

**A10 — Repo gates stay green.** `scripts/ci-local.sh` passes: both new scripts are stdlib-only Python 3.8+, and all new tests are pytest (no new `.bats`).

**A11 — Overwrites and writes are never silent.** The export reports the destination and count of files written; a re-export over existing derived files reports the overwrite count and removes (with a reported count) stale derived files no longer produced by the plan. Asserted by `plan_gherkin_export.py` unit tests.

**A12 — Write failures surface.** An export whose destination collides with a non-directory file, or whose plan file is unreadable, exits non-zero naming the offending path; `plan/SKILL.md` surfaces the failure instead of claiming success. Asserted by export unit tests + content-guard pytest.

**A13 — Detection failure falls back to no-signal.** `plan/SKILL.md` treats a non-zero detection exit as no-signal (prompt or headless skip) with stderr surfaced; planning continues. Asserted by content-guard pytest.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| Provenance header in derived `.feature` files vs byte-for-byte fidelity (conflict: issue's test sketch says byte-for-byte; `gherkin-derive` precedent writes headers) | `requires-stakeholder-input` | human | **No header — byte-for-byte** per the issue sketch. Header suggestion rejected: fidelity to the inline block and simpler diffing outweigh the derived-file marker; the plan metadata records the linkage instead. |
| When `/plan` writes the `.feature` files (issue is silent; constraint #1 forbids non-plan-file edits) | `requires-stakeholder-input` | human | **After human approval (step 6)**, as a narrow explicit carve-out to constraint #1. Unapproved scenarios never land in the tree; review-loop revisions never leave stale files. |
| Where detection runs — the issue references a "/plan Step 0 (Approach contract)" that does not exist in `plan/SKILL.md` | `inferable` | inference | Detection runs at plan creation (steps 2/3) so the destination is recorded in the plan and visible to reviewers and the human gate; the write is deferred to post-approval. |
| Non-interactive default when no signal is detected | `inferable` | inference | Plan-file-only (`n`) with a logged skip. `/plan` step 6 already establishes the never-block-headless doctrine and the same triad of triggers; the issue's own conservatism (false positive worse than false negative) picks the no-write default. |
| Detection as a shipped Python script vs prose-only skill instructions | `inferable` | inference | Shipped stdlib-only script, per ADR 0014 and direct precedent (`plan_waves.py`, `git_origin_host.py` — `/plan` already shells to scripts for deterministic sub-tasks). The issue's test-plan sketch requires per-stack deterministic detection, which only a testable script provides. |
| Multiple unrelated `.feature` roots, or conflicting manifest destinations (monorepo) | `inferable` | inference | Report `none` and fall through to the prompt — the issue states detection must be conservative and prefers a false negative. |
| Re-running `/plan` when derived files already exist | `inferable` | inference | Overwrite files under the same `<dir>/<plan-slug>/`: the plan file is the declared source of truth and the files are derived; issue frames them as write-once-at-`/plan`-time. |
| Vendored/generated trees in the `.feature` scan | `inferable` | inference | Excluded (`node_modules/`, `vendor/`, `dist/`, `build/`, virtualenvs, `.git/`) — a dependency's shipped `.feature` files are not the project's convention. |
| Filename scheme within the destination | `inferable` | inference | `<detected-dir>/<plan-slug>/slice-<N>-<slice-slug>.feature`, exactly as proposed in the issue; plan-slug derives from the plan filename. |
| Downstream commands (`/build`, `/continue`, guardian) reacting to derived files | `inferable` | inference | No change — nothing downstream parses `.feature` files today, and execution/CI wiring is explicitly out of scope. |
| Byte-for-byte copy executed by LLM prose vs a deterministic script | `inferable` | plan review (Design Critic) | Deterministic `plan_gherkin_export.py` reusing `scripts/lib/plan_parse.py` — mirrors the `plan_waves.py` shelling pattern and makes A7 unit-testable instead of trusted prose. |
| Overwrite scope when a manually created file sits at a destination path | `inferable` | plan review (Acceptance Critic) | `<dir>/<plan-slug>/` is tool-owned: anything inside is derived and overwritable (with a logged count); files outside it are never touched. |
| `/plan` behavior when the detection or export script fails mid-run | `inferable` | plan review (Acceptance + UX Critics) | Detection failure → no-signal fallback with stderr surfaced; export failure → reported as a failure, never claimed as success. |
| Custom-path (`c`) answer validation | `inferable` | plan review (UX Critic) | Validate repo-relative and non-vendored; re-prompt with the rejection reason rather than silently recording an unusable path. |

No finding was classified `LOW_VALUE`; every logged gap either changed the spec or resolved to an acceptance criterion.

## Consistency Gate

- [x] Intent is unambiguous — detection precedence, prompt behavior, timing, and fidelity are each pinned to a single interpretation
- [x] Every behavior/goal maps to an acceptance criterion (detection → A1–A4, A13; prompt → A5; non-interactive → A6; fidelity → A7, A11; timing → A8; decision record/re-run → A9; failure paths → A12–A13; repo constraints → A10)
- [x] Architecture constrains without over-engineering — two deterministic scripts, two skill-file edits, one template line; execution/sync explicitly out of scope
- [x] Terminology consistent across artifacts (signal, destination, derived files, plan-slug, persistence decision)
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — 2 resolved by human, 8 inferable with rationale

**Verdict: PASS**
