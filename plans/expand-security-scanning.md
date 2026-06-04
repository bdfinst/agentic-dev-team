# Plan: Expand Security Scanning with Language-Scoped Tools

**Created**: 2026-06-04
**Branch**: 38-feat-expand-security-scanning-with-language-scoped-tools
**Issue**: <https://github.com/bdfinst/agentic-dev-team/issues/38>
**Status**: revised after plan-review (acceptance/design/ux/strategic); code-review tiering formalized 2026-06-04 (per #38 = the `/code-review` security pre-pass)

## Goal

Extend the `static-analysis-integration` skill from its 5-tool Tier-1 baseline (semgrep,
gitleaks, trivy, hadolint, actionlint) to a 13-tool, capability-scoped, language-detected
pipeline. Add CodeQL, Bandit, ESLint+eslint-plugin-security, SpotBugs+Find Security Bugs,
Checkov, and Grype — each gated on detection of its target language or asset type. Update
two existing tools for restricted-egress environments: Gitleaks gains `--no-verify`, Trivy is
pinned to local-DB-only (`--skip-update --offline-scan`). Add three bespoke SARIF/JSON
adapters (Bandit, ESLint-security, SpotBugs), extend the deduplication priority chain, and
keep the unified finding envelope v1.0 output contract **unchanged** — only the scanner count
grows.

Because this pipeline is the **security pre-pass for `/code-review`** (diff-scoped, frequent,
non-gating), tools are **tiered by code-review cost**: most run inline on the diff every review,
while the heavyweight build-dependent tools (**CodeQL, SpotBugs**) run only under an explicit
`--deep` flag (or a scheduled/CI pass), never on a routine inline review.

The skill is a runtime instruction set read by the orchestrator/`/code-review`, not a program
that executes the tools itself. Therefore the deliverables are: (a) three executable Python
adapters with TDD coverage, (b) eval fixture pairs proving each new tool normalizes to
unified-finding-v1, and (c) precise, testable instruction prose in `SKILL.md` and
`tool-configs.md`. Static grep assertions and `/agent-audit` gate the prose; adapter unit
tests and `validate.py` gate the code.

**Honest verification boundary.** Some behaviors are executed by the AI orchestrator at runtime
by reading SKILL.md prose — they cannot be unit-tested here and are verified only by asserting
the prose is present, exact, and unambiguous. These are explicitly labelled **[prose-only,
behavior deferred to tier-2 nightly integration]** wherever they appear. The plan does not claim
a grep verifies a behavior; it claims a grep verifies the *instruction* exists. This distinction
is load-bearing — see the Verification Legend below.

Spec: GitHub issue #38 (the four-artifact spec is the source of truth for behavior).

### Delivery strategy (slicing)

The work decomposes along three risk seams and is intended to ship as **three sequential PRs**
against issue #38 (run `/issues-from-plan` after approval to track them). The unified-finding
envelope is frozen, so each slice is independently mergeable behind the same contract:

- **Slice A — offline-hardening** (Steps 6a + parts of 5): gitleaks `--no-verify`, trivy
  `--skip-update --offline-scan` + preflight DB-age check. Pure invocation-flag + prose. Lowest
  risk, highest immediate value (unblocks restricted-egress environments). Covers AC4, AC8, AC10,
  AC14.
- **Slice B — native-SARIF tools** (Steps 1, 1b, parts of 5/6): CodeQL/Checkov/Grype fixtures +
  parser changes + dedup-chain extension. Covers AC2-native, AC5, AC9, AC11, AC12, AC15, AC16.
  (Checkov + Grype are inline-tier; **CodeQL is deep-mode — `--deep`-only**.)
- **Slice C — bespoke adapters** (Steps 2–4, 4a): Bandit/ESLint/SpotBugs adapters + shared
  helper + tests. The only net-new executable code; carries the nightly adapter-drift obligation.
  Covers AC2-bespoke, AC6, AC7, AC13, AC16. (Bandit + ESLint-security are inline-tier; **SpotBugs is
  deep-mode — `--deep`-only**.) The second-maintainer gap is **deferred to the release gate** (see
  Risk 3), not a precondition on this slice.

If the human prefers a single PR, the step order below still applies; the slice tags mark where
the PR boundaries would fall.

## Verification Legend

Each AC and step is tagged with how it is verified, so the human gate can weight assurance:

- **[test]** — executable test asserts the behavior (adapter unit test or `validate.py` fixture).
- **[grep]** — static string assertion proves an instruction/flag/string is present and exact.
- **[prose-only]** — behavior is agent-executed at runtime; only the instruction is asserted
  here, behavioral correctness is deferred to the tier-2 nightly integration job. This is an
  acknowledged coverage gap, not a hidden one.

## Acceptance Criteria

Mapped 1:1 to the 15 acceptance criteria in issue #38. Verification tags reflect the revision.

- [ ] **AC1 — Language gate** `[test]+[prose-only]`: Each conditional tool runs only when its
  target file type/asset is present. **Detection logic itself is agent-executed prose** (the skill
  instructs the agent to `find` before dispatch); `validate.py` cannot run a "repo of files" and
  has no `tools_missing` logic. Verified by: (a) `[grep]` SKILL.md states, per tool, "skipped
  silently with no entry in tools_missing" for the no-matching-files branch; (b) `[prose-only]`
  the gate behavior is deferred to nightly integration. Step 1b adds a **detection-fixture harness**
  (`detect.py`) that exercises the file-glob → tool-set mapping against synthetic repo trees, so the
  *detection mapping* is `[test]`-covered even though end-to-end dispatch is prose. At code-review
  cadence the gate is **diff-aware** — a tool fires only when *changed files in scope* match its
  language (`[prose-only]`; repo-wide for `--all`/`--path`/clean-tree). See AC16.
- [ ] **AC2 — Schema conformance** `[test]`: Every new tool's findings validate against
  `unified-finding-v1.json`; a schema violation fails the run with tool name + rule id. Verified by
  per-adapter schema-valid, schema-violation, **and error-path** tests (Step 4a) plus `validate.py`
  for native-SARIF tools.
- [ ] **AC3 — Install hints, never failure** `[test]+[grep]`: Missing conditional tools produce
  install hints in the existing format; absence never fails the pipeline. Verified by extending
  `validate.py check_install_hints()` to cover the 6 new tools against `INSTALL_HINT_PATTERN`
  (Step 6b) + `[grep]` tool-configs.md contains each new tool's exact hint string.
- [ ] **AC4 — Gitleaks `--no-verify`** `[grep]`: invocation includes `--no-verify`; no outbound
  API calls. Verified by grep on SKILL.md Tier-1 table + tool-configs gitleaks block.
- [ ] **AC5 — CodeQL per-language DB** `[test]+[prose-only]`: one DB per detected compiled language;
  one language's build failure skips that language and continues others. Verified by: (a) `[test]`
  Step 1 fixture asserts the per-language rule_id segment (`codeql.java.<rule>`) after the parser
  change in Step 1; (b) `[grep]` SKILL.md contains exact warning `CodeQL database build failed —
  <lang> skipped`; (c) `[prose-only]` per-language build isolation deferred to nightly integration.
  **CodeQL is deep-mode** (`--deep`-only; see the code-review tiering constraint and AC16) — never
  run by a routine inline `/code-review`.
- [ ] **AC6 — SpotBugs build trigger** `[grep]+[prose-only]`: triggers a build when bytecode is
  absent; build failure warns (`SpotBugs skipped — build failed for JVM analysis`) and skips without
  failing the pipeline. `[grep]` exact warning present in SKILL.md; `[prose-only]` build-trigger
  behavior deferred to nightly integration. **SpotBugs is deep-mode** (`--deep`-only; see the
  code-review tiering constraint and AC16) — never run by a routine inline `/code-review`;
  build-triggering is one facet of deep-mode (see Risk 6).
- [ ] **AC7 — ESLint plugin gate** `[grep]+[prose-only]`: ESLint-security is skipped when
  `eslint-plugin-security` is not in `node_modules`, even if `eslint` is installed. `[grep]` SKILL.md
  contains the `require('eslint-plugin-security')` detection instruction; behavior is `[prose-only]`.
- [ ] **AC8 — Trivy offline** `[grep]`: runs with `--skip-update --offline-scan`; missing local DB
  warns with the **full** string `trivy local DB missing — run: trivy image --download-db-only`.
  Verified by grep for the complete string (not the prefix) in SKILL.md + tool-configs trivy block.
- [ ] **AC9 — Grype offline** `[grep]`: zero network calls; missing local DB warns with the full
  string `grype local DB missing — run: grype db update`. Verified by grep for the complete string.
- [ ] **AC10 — Stale DB warning** `[grep]`: Trivy/Grype DB > 7 days warns with day count, does not
  skip. Verified by grep for the full templated strings `trivy DB is N days old — consider refreshing
  with: trivy image --download-db-only` and `grype DB is N days old — consider refreshing with: grype
  db update`. The 7-day boundary is defined inclusively: mtime age ≤ 7d = fresh, > 7d = stale.
- [ ] **AC11 — Checkov + trivy-config on Dockerfiles** `[grep]+[prose-only]`: both scan Dockerfiles;
  duplicates deduped with trivy priority over checkov. Cross-tool dedup is **agent-executed prose**
  (no dedup code exists in the repo; the only dedup test is adapter-side). Verified by `[grep]`
  SKILL.md dedup section states trivy > checkov, and by the single-source priority artifact (Step 0);
  `[prose-only]` the runtime tie-break is deferred to nightly integration. The fictional "dedup
  fixture ordering test" from the prior draft is removed.
- [ ] **AC12 — Extended dedup chain** `[test]+[grep]`: `semgrep > codeql > gitleaks > bandit >
  eslint-security > spotbugs > trivy > checkov > grype > hadolint > actionlint`. The chain is
  extracted to a single machine-readable artifact (Step 0); `[test]` asserts the artifact matches
  this exact ordering and `[grep]` asserts SKILL.md references it — preventing prose/artifact drift.
  Application of the chain at runtime remains `[prose-only]`.
- [ ] **AC13 — Adapter LOC budget** `[test]`: each of the 3 new adapters ≤ 40 LOC, measured by an
  **AST-based logical-line counter** (module docstring and the shared-helper import line excluded;
  see Step 0 helper). The prior `grep -cvE` measure is replaced because it miscounts triple-quoted
  docstrings.
- [ ] **AC14 — Tier-1 unchanged except gitleaks/trivy** `[test]+[grep]`: semgrep, trivy-IaC,
  hadolint, actionlint behavior unchanged; all pre-existing tier-1 fixtures still pass `validate.py`
  unchanged, and `git diff` touches only the gitleaks/trivy tool blocks among Tier-1.
- [ ] **AC15 — Conditional `tools_missing`** `[test]+[prose-only]`: absent conditional tools listed
  only when their target language/asset is present. Both arms covered by Step 1b detection-fixture
  harness (binary-absent+files-present → entry expected; binary-absent+no-files → entry absent);
  end-to-end emission is `[prose-only]`.
- [ ] **AC16 — Code-review tiering (plan-added, beyond spec #38)** `[grep]+[prose-only]`: SKILL.md
  documents the inline vs `--deep` split and gates **CodeQL + SpotBugs behind `--deep`** (never fired
  by a routine inline `/code-review`), and detection is **diff-aware** at default (diff) scope.
  Verified by `[grep]` for the `--deep` gating instruction + the diff-aware-detection prose; runtime
  gating/scoping is `[prose-only]` (deferred to nightly integration). This formalizes #38's intent as
  the `/code-review` security pre-pass.
- [ ] `/agent-audit` passes for the modified skill; CLAUDE.md skill count/description need no change
  (skill name and role are unchanged).

## User-Facing Behavior

The complete Gherkin feature (`Expanded security scanning with language detection`, 28 scenarios)
lives in issue #38 and is the authoritative behavior spec. It is not duplicated here to avoid
drift; each implementation step below references the scenarios it satisfies. The plan adds the
following scenarios the spec did not enumerate (drafted in full in the linked review notes):
ESLint extension-segment inference (`.tsx`/`.mjs` → which segment), adapter error-path
(unparseable input), stale-DB 7-day boundary, and deduplicated-finding-counted-once. These are
added to the feature file as part of Slice B/C.

## Architecture Constraints (from the spec)

- **Output contract frozen**: all tools normalize to unified-finding-v1; no schema fields added.
- **Detection runs once per invocation, and is diff-aware at code-review cadence.** `/code-review`
  default-scopes to the uncommitted diff, so a conditional tool fires only when **changed files in
  scope** match its language/asset — not merely because the repo contains that language (otherwise a
  one-line CSS change in a Java monorepo would trigger a whole-repo Java scan). Detection is shared
  across overlapping tools (Java detection covers both CodeQL and SpotBugs). For full-repo runs
  (`--all`, `--path`, or a clean tree) detection is repo-wide.
- **Code-review tiering — inline vs `--deep`.** This skill is the SARIF pre-pass for `/code-review`,
  which runs frequently, on a diff, non-gating. Tools split into two cost tiers:
  - **Inline (default-on, diff-scopeable):** gitleaks, semgrep, bandit, eslint-security, hadolint,
    actionlint, trivy (config + fs), checkov, grype — run on every review.
  - **Deep-mode (opt-in `--deep` only):** **CodeQL** and **SpotBugs** — whole-project,
    build-dependent, minutes-slow, not diff-scopeable (the DB/build spans the whole codebase). They
    run **only** when the operator passes `--deep` (or in a scheduled/CI security pass), **never** on
    a routine inline `/code-review`. This subsumes the earlier "build-triggering is opt-in" decision:
    build-triggering is one facet of deep-mode.
- **Adapters ≤ 40 LOC each** of *tool-specific mapping logic*. Shared validate-before-emit /
  schema-load / argparse machinery lives in `adapters/_envelope.py` (Step 0) and is excluded from
  the per-adapter count — the same way blank/comment lines are excluded. Bespoke only where upstream
  has no native SARIF (Bandit, ESLint, SpotBugs). CodeQL, Checkov, Grype emit native SARIF → no
  adapter, fixtures + `TOOL_TIER_MAP` entry only.
- **Offline enforcement is preflight**: DB-path-exists + `mtime age ≤ 7 days`. Absent → skip+warn;
  stale → run+warn. Neither is a hard failure.
- **Tier placement** (per spec table): CodeQL/Bandit/ESLint/SpotBugs/Checkov/Grype → Tier 2;
  Gitleaks/Trivy stay Tier 1 (updated invocations).
- **Canonical tool tokens** (resolves terminology drift): each tool has ONE user-facing token used
  identically in the finding `metadata.source`, the dedup chain, and the install-hint name slot.
  Tokens: `eslint-security`, `spotbugs`, `codeql`, `checkov`, `grype`, `bandit`. Rule_id prefixes
  use the same token (`eslint-security.<js|ts>.<rule>`, `spotbugs.java.<type>`, etc.). Capability
  descriptions may elaborate ("ESLint + eslint-plugin-security") but the token never varies.

## Non-Goals

Consolidated so they bind the implementer and are visible at the gate:

1. **No ESLint config-wiring verification** — the gate checks `eslint-plugin-security` package
   presence only, not whether it is enabled in the active flat-config/eslintrc.
2. **No integration/runtime coverage** for CodeQL per-language orchestration, SpotBugs build-trigger,
   detection-gate end-to-end dispatch, or cross-tool dedup application — these are `[prose-only]`,
   deferred to a future tier-2 nightly integration job.
3. **No new unified-finding schema fields** — the envelope is frozen at v1.0.
4. **No changes to non-gitleaks/trivy Tier-1 tools** (semgrep, hadolint, actionlint).
5. **No auto-install of any tool** — missing tools produce install hints only.
6. **No deep-mode tools at inline review cadence** — CodeQL and SpotBugs are `--deep`-only and never
   silently trigger a project build. A routine `/code-review` runs only the inline tier; deep-mode is
   an explicit opt-in or a scheduled/CI pass. See the code-review tiering constraint above and AC16.

## Steps

Ordering: shared scaffolding (Step 0) → code-with-tests (Steps 1–4a) → instruction prose
(Steps 5–6b) → whole-spec acceptance replay (Step 7). Every prose claim is backed by a landed,
tested artifact or explicitly tagged `[prose-only]`.

### Step 0: Shared scaffolding — envelope helper, priority artifact, LOC counter

**RED** — Add `evals/static-analysis-tools/test_priority_chain.sh` asserting a not-yet-existing
priority artifact equals the AC12 ordering; add `evals/static-analysis-tools/test_loc_budget.py`
(AST-based logical-line counter) run against a fixture. Both fail (artifacts/helper absent).

**GREEN** —

1. Create `plugins/dev-team/knowledge/static-analysis-dedup-priority.json` — the single
   machine-readable source for the dedup priority chain (ordered array). SKILL.md's dedup section
   references this file by path so prose and artifact cannot drift (AC12).
2. Create `adapters/_envelope.py` exposing `load_validator()`, `validate_or_die(finding, tool)`
   (stderr ERROR with tool name + rule id, exit 1 on schema violation), and an
   `argparse(--input,--output)` builder. Extracted from the duplicated machinery in
   `security-review-adapter.py`; single-sourced so all three new adapters import it.
3. Create the AST-based LOC counter (`test_loc_budget.py`): counts logical statements, excludes the
   module docstring and `from _envelope import ...`. This is the AC13 measure.

**REFACTOR** — Optionally migrate `security-review-adapter.py` to import `_envelope.py` if it lands
within the existing test suite green (nice-to-have; not required).

*Covers: dedup single-source-of-truth, adapter machinery, LOC measurement.*
*Verifies: AC12 `[test]`, AC13 `[test]` (harness), enables AC2 `[test]`.*

### Step 1: Native-SARIF fixtures + parser language-segment support (CodeQL, Checkov, Grype)

Resolves the design blocker: the current `validate.py build_rule_id` produces `<driver>.<tier>.<rule>`
and does **not** read `properties.language`, so a fixture asserting `codeql.java.sql-injection` is
unimplementable without a parser change. `references/sarif-parser.md:11` already documents the
language-middle-segment as the contract — so this step makes the implementation match the documented
contract rather than forbidding the change.

**RED** — Add fixture pairs (`mock.sarif` + `expected-findings.json`) for `codeql`, `checkov`,
`grype` under the fixtures dir chosen in the taxonomy decision below. The CodeQL fixture sets
`results[].properties.language: "java"` and expects `rule_id: "codeql.java.<rule>"`. Run
`validate.py`; it fails (no `TOOL_TIER_MAP` entry; no language-segment logic).

**GREEN** —

1. Extend `TOOL_TIER_MAP`: `"codeql": "sast"`, `"checkov": "iac"`, `"grype": "supply-chain"`.
2. Add a `properties.language` branch to `build_rule_id` (mirroring the existing tier-override seam):
   when set, insert it as the middle segment → `<driver>.<language>.<rule>`; otherwise fall back to
   `<driver>.<tier>.<rule>`. Update `sarif-parser.md` to mark this as **implemented**, not aspirational.
3. **Fixture taxonomy decision**: these are Tier-2 tools but `validate.py` currently iterates only
   `tier1-mocks/`. Rename `MOCKS_DIR`'s directory to the tier-neutral `sarif-mocks/` (update
   `validate.py`, `maintenance.md`'s "Adding a tool" policy, and the two SKILL.md eval-path
   references), and place all new fixtures there. This removes the "Tier-2 tool in a tier1 folder"
   inconsistency the design review flagged. Existing tier-1 fixtures move with the rename; their
   `expected-findings.json` are unchanged (preserves AC14).

**REFACTOR** — Confirm pre-existing tier-1 fixtures still pass byte-identical after the rename and
the language-segment branch (they carry no `properties.language`, so output is unchanged).

*Covers: CodeQL, Checkov, Grype normalization.*
*Verifies: AC2-native `[test]`, AC5 rule_id `[test]`, AC14 `[test]` (regression).*

### Step 1b: Detection-fixture harness (`detect.py`)

Makes the language-detection *mapping* executable instead of pure prose, addressing the AC1/AC15
blocker without pretending to test end-to-end dispatch.

**RED** — Add `evals/static-analysis-tools/detection/` with synthetic repo trees (python-only,
js+ts, java+kotlin, iac-only, empty) and `test_detection.py` asserting the file-glob → expected
tool-set and the `tools_missing` inverse-conditional for each tree. Fails (no `detect.py`).

**GREEN** — Add `detect.py`: given a root path and a tool→glob map, returns
`{tool: present_bool}` and computes `tools_missing` = tools whose files are present but binary is
absent (binary presence injected as a param for testability). This is the single source for the
detection mapping that SKILL.md prose describes; the harness asserts both arms of AC15.

**REFACTOR** — Ensure the glob map is data, not branching, so adding a future tool is a one-line
table entry.

*Covers: language-gate scenarios (mapping side).*
*Verifies: AC1 `[test]` (mapping), AC15 `[test]` (both arms); end-to-end dispatch stays `[prose-only]`.*

### Step 2: Bandit adapter (`bandit-adapter.py`)

**RED** — Add `bandit` fixtures and `evals/bandit-adapter/tests/` modeled on
`evals/security-review-adapter/tests/`: `test_adapter_positive.sh`, `test_adapter_schema_valid.sh`,
`test_adapter_schema_violation_fixture.sh`, plus the LOC budget assertion from Step 0. Tests invoke
the not-yet-existing `adapters/bandit-adapter.py --input <bandit.json> --output <jsonl>`.

**GREEN** — Write `adapters/bandit-adapter.py` importing `_envelope.py`. Reads `bandit -r <path>
-f json` (`results[]`: `filename`, `line_number`, `test_id`, `issue_severity`, `issue_confidence`,
`issue_text`). Maps: `rule_id = "bandit.python.<test_id_lower>"`, severity `HIGH→error`,
`MEDIUM→warning`, `LOW→suggestion`, `metadata.confidence` from `issue_confidence`. Calls
`validate_or_die` before emit. With `_envelope.py` doing the machinery, tool-specific logic is well
under 40 logical lines.

**REFACTOR** — Keep mapping a flat dict where possible.

*Covers: Bandit scenarios.*
*Verifies: AC2 `[test]`, AC13 `[test]`.*

### Step 3: ESLint-security adapter (`eslint-security-adapter.py`)

**RED** — Fixtures + `evals/eslint-security-adapter/tests/` (same set as Step 2, **plus** the
extension-segment boundary cases: `.ts`/`.tsx`/`.mts` → `ts`; `.js`/`.jsx`/`.mjs`/`.cjs` → `js`;
unrecognized extension → documented fallback `js`). Sample input has a `security/detect-child-process`
hit.

**GREEN** — Write `adapters/eslint-security-adapter.py` importing `_envelope.py`. ESLint JSON is an
array of file objects (`filePath` + `messages[]`: `ruleId`, `line`, `column`, `severity` 1/2,
`message`). Map: `rule_id = "eslint-security.<js|ts>.<ruleId>"` (canonical token; segment from a
small extension table), severity `2→error`, `1→warning`. `ruleId == null` (parse errors) skipped.
`validate_or_die` before emit.

**REFACTOR** — As Step 2.

*Covers: ESLint scenarios (normalization side; plugin-presence gate is Step 5 prose).*
*Verifies: AC2 `[test]`, AC13 `[test]`.*

### Step 4: SpotBugs adapter (`spotbugs-adapter.py`)

**RED** — Fixtures + `evals/spotbugs-adapter/tests/`. Sample is `spotbugs -xml` with an FSB
`BugInstance` (e.g. `SQL_INJECTION_JDBC`), **plus** a BugInstance whose `SourceLine` children lack
`sourcepath` (Risk 1 variance).

**GREEN** — Write `adapters/spotbugs-adapter.py` importing `_envelope.py`. Parse XML with stdlib
`xml.etree.ElementTree`: `BugInstance/@type`, `@priority` 1/2/3, first `SourceLine` with a
`sourcepath` (fallback to `Class/SourceLine`; if none, skip with a warning — never emit
schema-invalid), `LongMessage`. Map: `rule_id = "spotbugs.java.<type_lower>"`, priority `1→error`,
`2→warning`, `3→suggestion`. `validate_or_die` before emit.

**REFACTOR** — As Step 2.

*Covers: SpotBugs scenarios (XML parsing side; build-trigger is Step 5 prose).*
*Verifies: AC2 `[test]`, AC13 `[test]`.*

### Step 4a: Adapter error-path tests (all three)

Adds the error-path coverage the existing `security-review-adapter` has but the prior draft omitted.

**RED/GREEN** — For each new adapter add: `test_adapter_unparseable_input.sh` (malformed JSON/XML →
exit non-zero, stderr names the tool), `test_adapter_empty_input.sh` (empty array / no BugInstance →
exit 0, zero findings). Adapters already satisfy these via `_envelope.py` + defensive parsing; tests
lock the behavior.

*Covers: adapter error/empty paths.*
*Verifies: AC2 error-path `[test]`.*

### Step 5: `SKILL.md` — tiers, language gate, offline enforcement, dedup chain

Prose changes verified by `[grep]`; behavioral correctness of agent-executed items is `[prose-only]`.

1. **Tier tables** — Tier-1: gitleaks `... --no-verify`; trivy `... --skip-update --offline-scan`.
   Replace the Tier-2/3 placeholders with the real table (canonical tokens; conditions; adapter
   refs). **Remove the Tier-4 legacy ESLint entry** and drop legacy-ESLint from the dedup
   parenthetical — `eslint-security` is now its single identity (resolves the design double-identity
   warning; keep tsc/pylint as the only legacy parenthetical).
2. **Language detection gate (diff-aware)** — Under `### 1. Detect available tools`: detection runs
   once via `find` (references `detect.py`'s mapping as the canonical glob table); shared across
   overlapping tools; no-matching-files → skipped silently, **no** `tools_missing` entry;
   files-present + binary-absent → `tools_missing` entry. State both arms verbatim per tool. **At
   default (diff) scope, gate each tool on changed files in scope, not repo-wide presence**; repo-wide
   for `--all`/`--path`/clean-tree. `[prose-only]` dispatch. (AC16)
3. **Tool tiering — inline vs `--deep`** — Document the two tiers explicitly: inline tools run on
   every review; **CodeQL and SpotBugs run only under `--deep`** (or scheduled/CI), never on a routine
   inline `/code-review`. State the `--deep` flag and that the inline tier stays read-only/fast. (AC16)
4. **CodeQL per-language DB strategy (deep-mode)** — Behind `--deep` only. `codeql database create
   --language=<lang> --command=<build>` per detected compiled language, parallel; build defaults
   (`mvn clean package -DskipTests`, `gradle build -x test`, `dotnet build`); per-language failure →
   exact warning `CodeQL database build failed — <lang> skipped`, continue others. Build-triggering
   is a facet of deep-mode (Non-Goal 6).
5. **SpotBugs build trigger (deep-mode)** — Behind `--deep` only. Absent `.class`/JAR → detect build
   tool (`pom.xml`→Maven, `build.gradle`→Gradle); failure → exact warning `SpotBugs skipped — build
   failed for JVM analysis`, skip without failing pipeline. Non-Goal 6.
6. **ESLint detection** — `command -v eslint` AND `node -e "require('eslint-plugin-security')"`;
   both pass or skip (plugin-missing → install hint). Note flat-config limitation (Risk 4).
7. **Offline enforcement (Trivy, Grype)** — preflight DB-path + `mtime age ≤ 7d`; absent → skip+warn
   with the **full** strings; stale (> 7d) → run+warn with the **full** templated strings. Quote all
   four verbatim:
   - `trivy local DB missing — run: trivy image --download-db-only`
   - `trivy DB is N days old — consider refreshing with: trivy image --download-db-only`
   - `grype local DB missing — run: grype db update`
   - `grype DB is N days old — consider refreshing with: grype db update`
8. **Extended dedup chain** — replace the chain line; reference
   `knowledge/static-analysis-dedup-priority.json` (Step 0) as the source. Exact ordering:
   `semgrep > codeql > gitleaks > bandit > eslint-security > spotbugs > trivy > checkov > grype >
   hadolint > actionlint`. Add the "deduplicated finding counted once, attributed to surviving tool"
   note to the summary section.

*Covers: control-flow narrative; dedup; output-contract-unchanged.*
*Verifies: AC1/AC5/AC6/AC7/AC11/AC15 `[grep]` (instruction present), AC4/AC8/AC9/AC10/AC12 `[grep]`.*

### Step 6: `tool-configs.md` + install-hint coverage

**6a (Slice A) — Tier-1 updates**:

1. gitleaks block: add `--no-verify`; note "no outbound API calls to verify secrets."
2. trivy block: add `--skip-update --offline-scan` to both `config` and `fs`; document the preflight
   DB check and the two full warning strings.

**6b (Slice B/C) — Tier-2 blocks + hint coverage**:
3. Replace the Tier-2 placeholder with real blocks for CodeQL, Bandit, ESLint+plugin, SpotBugs+FSB,
   Checkov, Grype: invocation, detection check, install hint, capability tier, adapter ref. For
   **compound installs**, write the exact rendered hint and confirm it fits the format section —
   decide one-line two-package form, e.g.:

- `eslint-security — JS/TS security linting. install: npm i -D eslint eslint-plugin-security`
- `spotbugs — JVM security analysis. install: brew install spotbugs && <FSB plugin install>`
     (specify the real FSB plugin path; `brew install spotbugs` alone under-scans silently).
   Add a compound-hint example to SKILL.md's "Install-hint format" section so the shape is documented.

1. Extend `validate.py check_install_hints()` to include the 6 new conditional tools, update the
   hardcoded count/message, and assert each new hint against `INSTALL_HINT_PATTERN`.

*Covers: install-hint + invocation detail for all new tools.*
*Verifies: AC3 `[test]+[grep]`, AC4 `[grep]`, AC8/AC9 `[grep]`, AC14 `[test]`.*

### Step 7: Final acceptance replay + maintenance compliance

1. `python3 evals/static-analysis-tools/validate.py` — all fixtures (old + new) pass.
2. Run every new adapter + detection + priority + LOC test; confirm green.
3. `/agent-audit` on the skill; confirm structural compliance.
4. Run the full Pre-PR assertion block (below) — every machine-assertable AC asserts true; confirm
   the `[prose-only]` items are present and exact (not behaviorally tested — that is the documented
   gap).
5. `maintenance.md` "Adding a tool" policy satisfied for each new tool (fixture pair + adapter where
   required). Second-maintainer gap logged for the release gate, not blocking here (Risk 3).
6. `git diff` touches only gitleaks/trivy blocks among Tier-1 (AC14).

*Verifies: AC1–AC15 in aggregate, per their tags.*

## Complexity Classification

**Moderate.** No new runtime architecture — the skill, parser, and envelope contract already exist
and are unchanged in shape. Net-new executable code is three small adapters (each importing a shared
`_envelope.py`, so each is genuinely ~40 logical lines of tool-specific mapping), a detection-mapping
harness, and a priority artifact. The native-SARIF tools are nearly free (fixture pair + one tier-map
line + a small parser branch). The largest residual risk is the set of `[prose-only]` behaviors
(detection dispatch, CodeQL/SpotBugs orchestration, dedup application) — honestly scoped as deferred
to nightly integration rather than claimed as tested.

## Pre-PR Quality Gate

```bash
SAI=plugins/dev-team/skills/static-analysis-integration
SKILL=$SAI/SKILL.md
CFG=$SAI/references/tool-configs.md

# 1. Parser + native-SARIF fixtures + detection + priority harnesses
python3 evals/static-analysis-tools/validate.py
python3 evals/static-analysis-tools/detection/test_detection.py
bash    evals/static-analysis-tools/test_priority_chain.sh

# 2. Bespoke adapter test suites (incl. error-path)
for d in bandit-adapter eslint-security-adapter spotbugs-adapter; do
  for t in evals/$d/tests/*.sh; do bash "$t" || echo "FAIL: $t"; done
done

# 3. Adapter LOC budget (AC13) — AST logical lines, docstring + helper-import excluded, ≤ 40
for a in bandit eslint-security spotbugs; do
  python3 evals/static-analysis-tools/test_loc_budget.py "$SAI/adapters/$a-adapter.py" 40
done

# 4. AC grep assertions — FULL strings, not prefixes
grep -q -- '--no-verify' "$CFG"                                   # AC4
grep -q -- '--skip-update --offline-scan' "$CFG"                  # AC8
grep -qF 'trivy local DB missing — run: trivy image --download-db-only' "$SKILL"          # AC8
grep -qF 'grype local DB missing — run: grype db update' "$SKILL"                          # AC9
grep -qF 'trivy DB is N days old — consider refreshing with: trivy image --download-db-only' "$SKILL"  # AC10
grep -qF 'grype DB is N days old — consider refreshing with: grype db update' "$SKILL"     # AC10
grep -qF 'CodeQL database build failed — ' "$SKILL"               # AC5
grep -qF 'SpotBugs skipped — build failed for JVM analysis' "$SKILL"  # AC6
grep -qF "require('eslint-plugin-security')" "$SKILL"             # AC7
grep -qF 'semgrep > codeql > gitleaks > bandit > eslint-security > spotbugs > trivy > checkov > grype > hadolint > actionlint' "$SKILL"  # AC12
grep -qF 'static-analysis-dedup-priority.json' "$SKILL"          # AC12 single-source ref
grep -qF -- '--deep' "$SKILL"                                     # AC16 deep-mode gating present
grep -qiE 'changed files in scope|diff-aware' "$SKILL"           # AC16 diff-aware detection
for t in codeql bandit eslint-security spotbugs checkov grype; do  # AC3 hints present
  grep -q "^$t — " "$CFG" || echo "MISSING HINT: $t"
done

# 5. Tier-1-unchanged regression (AC14): no diff to semgrep/hadolint/actionlint blocks
git diff --unified=0 origin/main -- "$CFG" | grep -E '^\+' | grep -Eiq 'semgrep|hadolint|actionlint' \
  && echo "AC14 VIOLATION: non-gitleaks/trivy tier-1 block changed" || echo "AC14 ok"

# 6. Structural compliance
# /agent-audit   (run via slash command in-session)
```

All machine-assertable checks green before opening each PR. PR body links issue #38, lists the AC
checklist with verification evidence, and **explicitly names the `[prose-only]` ACs as deferred** so
the human reviewer weights them correctly.

## Risks & Open Questions

1. **SpotBugs XML schema variance** — FSB `BugInstance` layouts vary (multiple `SourceLine`, missing
   `sourcepath`). Mitigation: fixture pins the minimal contract; adapter takes the first `SourceLine`
   with `sourcepath`, falls back to `Class/SourceLine`, skips with a warning if neither (never emits
   schema-invalid). Covered by Step 4 + 4a tests. Flagged in the adapter docstring.
2. **`[prose-only]` behaviors are not integration-tested** — detection dispatch, CodeQL per-language
   orchestration, SpotBugs build-trigger, and cross-tool dedup application are agent-executed and
   verified only by exact-instruction grep here. Real behavioral coverage requires a tier-2 nightly
   integration job (out of scope for #38, recommended as a follow-up). This is the plan's largest
   acknowledged coverage gap and is surfaced at the human gate, not hidden.
3. **`maintainers:` bus-factor** — frontmatter still lists `unassigned` as the second maintainer;
   adding six tools triples the adapter-drift surface. **Decision (made):** the second-maintainer
   gap is **deferred to the release gate** — this change proceeds with bus-factor 1, knowingly
   accepting the policy gap, and the gap is logged for resolution before release rather than
   blocking any slice. Revisit if the nightly adapter-drift load proves unsustainable.
4. **ESLint flat-config vs eslintrc** — package presence is checked, not active-config wiring (Non-Goal
   1). Documented limitation in the ESLint block.
5. **Trivy flag compatibility** — `--offline-scan` skips network vuln matching; `--skip-update`
   prevents DB download. Both valid together on trivy ≥ 0.50; note the minimum version in the block.
6. **Deep-mode tools inside a read-only pre-pass** — auto-running `mvn`/`gradle`/`dotnet build`
   (CodeQL/SpotBugs) expands what the pre-pass does (build-time, build-side-effects, possible
   `/code-review` stalls). **Decision (made):** CodeQL and SpotBugs are **deep-mode** — gated behind an
   explicit `--deep` flag (or a scheduled/CI pass), never fired by a default inline `/code-review`. The
   inline tier stays read-only and fast. Intent confirmed: #38 is the `/code-review` security pre-pass
   (see the code-review tiering constraint and AC16).

```
