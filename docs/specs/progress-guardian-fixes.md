<!-- spec-version: 1 -->
# Spec: progress_guardian — fix four pre-PR gate false positives

**Format:** dev-team specs v1
**Issue:** <https://github.com/bdfinst/agentic-dev-team/issues/525>

## Intent Description

`scripts/progress_guardian.py` is the pre-PR gate run by `/pr` (and the `progress-guardian` agent) to prove that a branch's plan is complete, every `[x]` step has a matching commit, and the branch hasn't sprawled outside its declared file scope. It is supposed to *catch* plan-discipline failures. Today it fires on every Conventional-Commits-following branch with a normal `## Build Progress` + `## Acceptance Criteria` plan layout — producing noise that trains contributors to ignore the gate, the exact failure mode the gate exists to prevent.

The root cause is **four** false-positive bugs (three identified upfront in issue #525 and a fourth discovered during build):

1. **`check_scope` prefers stale local `main` over `origin/main`** (pre-fix line 248). Local `main` lags `origin/main` from the moment any work begins; the resulting merge-base sweeps in every commit landed on trunk while the contributor worked, producing dozens of false "out-of-plan file" warnings.
2. **`check_commit_discipline` requires a substring of the plan-step header in commit subjects** (pre-fix lines 156–170). CLAUDE.md mandates Conventional Commits (`feat(scope): summary`); plan headers like *"Wire stack detection into test-smell-review"* never appear verbatim in `feat(test-smell-review): detect stack from manifests…`. The matcher and the repo's own commit policy structurally collide.
3. **`parse_plan` scans every checkbox in the file** (pre-fix lines 32, 110–126). The `## Acceptance Criteria` section uses the same `- [ ]` syntax as `## Build Progress`, so the pre-PR gate then demands each AC be `[x]` — producing false "Pre-PR gate: step 'A1: …'" findings on plans where the AC list is correctly aspirational.
4. **`parse_plan` also reads the `### Acceptance Criteria` mirror inside `## Build Progress`.** Discovered during build: the `/plan` skill's Build Progress template renders a documentation-only mirror of the top-level AC list. With Change 3 narrowing parse_plan to the Build Progress section, that mirror still trips the gate. Fixed in-place by extending the section anchor with an inner skip for the H3 AC sub-heading. The underlying structural issue — that AC items are checkbox-tracked without work-tracking semantics — is tracked separately as **issue #526** for future redesign; this PR ships the workaround.

This change fixes all four with the minimum-blast-radius implementations chosen in the approach contract: tuple reorder for (1), file-path matching for (2), `## Build Progress` heading anchor for (3), inner H3 skip for (4). Each fix is independent and additive; none break existing passing fixtures.

Pre-fix line numbers above reference the script's state on `origin/main` at the start of this PR. After the fix the `check_scope` tuple lives inside the new `_branch_base_sha` helper, and `check_commit_discipline` spans roughly 247-340 with two new helpers added above it.

## Architecture Specification

**Single file edited:** `scripts/progress_guardian.py`. No new modules, no helper-script extraction, no public-API changes — the script's three CLI flags (`--plan`, `--pre-pr`, `--skip-llm`) and three exit codes (`0` pass, `1` fail, `2` warn) are unchanged.

**Test files touched:** `tests/scripts/progress_guardian_tests.bats` (extended with regression coverage for all four bugs — the original three regression sections 4.1–4.3 plus `4.3-mirror` for bug 4). The existing 11 `@test` blocks must remain green.

**Change 1 — `check_scope`: prefer remote tracking refs.**

```python
# Before (line 248)
for branch in ("main", "master", "origin/main", "origin/master"):

# After
for branch in ("origin/main", "origin/master", "main", "master"):
```

Pure tuple reorder. Behavior is unchanged in the fully-fresh case (origin/main == main), and corrected in the realistic case (origin/main is ahead of local main). No network call added — relies on whatever the local clone's tracking ref already says.

**Change 2 — `check_commit_discipline`: switch to file-path matching.**

Replace substring matching of step headers against commit subjects with: parse each slice's `**Files:**` line from the plan, and for each `[x]` slice verify at least one commit since branch base touched at least one of those declared files. A slice "is committed" iff there's a commit on the branch that modified one of its declared files. Commit subjects can use any wording — Conventional Commits, descriptive sentences, or anything else.

Plan-format contract: `/plan` emits per-slice `**Files:**` lines as bulleted-or-bold text like `**Files:** \`path/one\`, \`path/two\``. The matcher reads backtick-quoted paths from each`**Files:**` line. When a slice has no `**Files:**` line, the matcher falls through to the existing substring matcher (covers legacy plans + minimal plans where steps don't declare files).

Branch base resolution reuses `check_scope`'s logic (prefer `origin/main`).

**Change 3 — `parse_plan`: anchor on `## Build Progress`.**

When the plan contains a `## Build Progress` heading, only parse checkbox lines *between that heading and the next H2 (or EOF)*. When the plan has no `## Build Progress` heading (legacy or minimal plan), fall back to whole-file scanning — preserves backward compatibility with the existing test fixtures (the 11 existing `@test` blocks construct minimal plans with no Build Progress section).

This narrows the gate to where the `/plan` skill actually stores step-completion state.

**Change 4 — `parse_plan`: skip the `### Acceptance Criteria` mirror inside Build Progress.**

Discovered during build. The `/plan` skill's Build Progress template renders an inner mirror of the top-level AC list under a `### Acceptance Criteria` H3 subheading. Those mirror items have no `### Slice N:` heading and no `**Files:**` line, so the file-path matcher (Change 2) and the substring fallback both fail — manifesting as "no matching commit" errors for every AC item. `parse_plan` now carries a second flag (`in_acceptance`) alongside `in_build_progress`: when an H3 named exactly `### Acceptance Criteria` is seen inside the Build Progress section, the inner-skip flag flips on and stays on until either another H3 opens or the section closes on its next H2. The legacy whole-file fallback is unaffected. **Issue #526** tracks the structural redesign of how ACs live in plans (operator evidence, per-AC verify commands, or removing the mirror entirely); this PR ships the surgical workaround so the gate stops false-positiving today.

**Constraints:**

- All 11 existing bats tests in `tests/scripts/progress_guardian_tests.bats` must remain green — these document the contract for minimal plans without `## Build Progress` or `**Files:**` lines.
- New tests live in the same bats file (one section per regression). Each uses a tmp git repo with synthetic commits, mirroring the existing helper pattern (`make_plan` + `git init -q` + synthetic commits).
- Exit codes (`0` / `1` / `2`) and JSON output schema (`{"status", "issues": [{"severity", "confidence", "file", "line", "message", "suggestedFix"}]}`) are unchanged. The `progress-guardian` agent and `/pr` skill consume this surface — breaking it ripples.
- `--skip-llm` flag and behavior unchanged.
- No new dependencies. Python 3 stdlib only (matches the existing script).

**Out of scope (rejected explicitly, do not bundle):**

- No `git fetch` added to refresh `origin/main` before merge-base. Approach contract resolved this as "additive only" — the cost of network in the gate exceeds the marginal value over "trust the tracking ref."
- No scope-token matching against Conventional Commit `feat(scope)` syntax. File-path matching is the chosen strategy; scope-token was rejected in the approach contract as fragile for slices whose title doesn't translate cleanly.
- No structural refactor of `progress_guardian.py` (no class extraction, no module split). The four changes are surgical edits in the existing function bodies.
- No redesign of where AC items live in plan files — tracked in **issue #526**. The Change 4 workaround makes the gate pass on plans the `/plan` skill emits today; the underlying "ACs lack work-tracking semantics" problem is left to a separate spec.
- No changes to the `progress-guardian` agent's prompt template (`plugins/dev-team/agents/progress-guardian.md`). The agent uses the script's output verbatim — fixing the script fixes its findings.
- No changes to other plan-consuming tools (`build-wave.sh`, `plan-waves.sh`, etc.). They parse plans for different purposes and aren't affected.

**Risk surface:**

- Test 3.2a in the existing suite asserts `[x] Step 1.1: add checkbox parser` + commit `feat: add checkbox parser` exits 0 under the substring matcher. Under the new file-path matcher with no `**Files:**` declared, the substring fallback must still fire — the test must remain green. (This is the explicit fallback in Change 2.)
- The plan-file format `**Files:** \`a\`, \`b\`` is a `/plan` convention, not a hard syntax requirement on every plan. The fallback to substring matching protects legacy plans.

## Acceptance Criteria

Each criterion is a deterministic, observable check.

**A1 — Stale-main fix (`check_scope`).**

- Source check: `scripts/progress_guardian.py` contains the literal tuple `("origin/main", "origin/master", "main", "master")` (in that order). Grep: `grep -F '"origin/main", "origin/master", "main", "master"' scripts/progress_guardian.py` returns ≥ 1.
- Behavioral check via new bats test: in a tmp repo where local `main` lags `origin/main` (simulated with a separate "remote" bare repo and `git push`/`git fetch` to set up the divergence), `progress_guardian --skip-llm` against a plan declaring files A and B, with the branch touching only A and B, reports zero out-of-plan files. The same scenario under the old tuple order would report files that landed on `main` while the branch was working.

**A2 — Conventional-Commits compatible matcher (`check_commit_discipline`).**

- Behavioral check via new bats test: plan with `## Build Progress` containing `- [x] Slice 1: …` and a `**Files:** \`a.py\`` line. Branch has a single commit `feat(scope): wording unrelated to the plan header` that modified `a.py`.`progress_guardian --skip-llm` exits 0. (Under today's matcher this exits 1 with "no matching commit.")
- Behavioral check via new bats test: same setup, but the commit modifies `b.py` (not declared). `progress_guardian --skip-llm` exits 1 with "no matching commit" — the matcher still catches actual undisciplined work.
- Behavioral check (fallback path) via existing test 3.2a: when no `**Files:**` line exists, the substring matcher still runs and the test stays green.

**A3 — Build Progress anchor (`parse_plan`).**

- Behavioral check via new bats test: plan with both `## Build Progress` (one `[x]` slice with matching commit) and `## Acceptance Criteria` (several `[ ]` AC items). `progress_guardian --pre-pr --skip-llm` exits 0 — the AC checkboxes are ignored.
- Behavioral check via new bats test: same plan but the `## Build Progress` slice is `[ ]`. `progress_guardian --pre-pr --skip-llm` exits 1 naming the unchecked slice.
- Behavioral check (fallback path) via existing test 3.3a: minimal plan with no `## Build Progress` heading — every checkbox in the file is parsed (today's behavior). Test stays green.

**A3b — AC mirror inside Build Progress is skipped (Change 4 / #526 workaround).**

Discovered during build. Plan with a `### Acceptance Criteria` H3 sub-heading inside `## Build Progress` containing `[ ]` AC mirror items, plus an outer `[x]` slice with a matching commit. `progress_guardian --pre-pr --skip-llm` exits 0 — the inner AC mirror items are ignored. Verified by bats test `4.3-mirror`. Structural redesign of where ACs live in plans is tracked in **issue #526**; this criterion only locks in the workaround.

**A4 — Real-world reproduction passes.**

- Manual verification step run from the #524 branch (or any future branch with the same plan layout): `python3 scripts/progress_guardian.py --pre-pr --plan plans/stack-aware-reference-loading.md` exits 0. PR description captures the before/after output as evidence.

**A5 — Existing test suite remains green.**

- `bats tests/scripts/progress_guardian_tests.bats` exits 0 (all 11 pre-existing tests + new tests added in this PR all pass).
- `bash scripts/ci-local.sh` exits 0.

**A6 — CI/release hygiene.**

- PR title `fix(progress-guardian): correct four pre-PR gate false positives (#525)` — `fix:` prefix for release-please patch bump.
- PR opened with `--no-auto-merge` per CLAUDE.md (touches `scripts/`).
- `/code-review` passes after auto-fix loop.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| Matcher strategy: substring / file-path / scope-token / either | `requires-stakeholder-input` | human (approach contract) | File-path match against the slice's declared `**Files:**` line. No scope-token, no permissive fallback. |
| STEP_PATTERN scope | `requires-stakeholder-input` | human (approach contract) | Anchor on `## Build Progress` heading, scan until next H2. |
| Stale-main fix scope | `requires-stakeholder-input` | human (approach contract) | Pure tuple reorder, no `git fetch`. |
| Behavior when plan has no `## Build Progress` heading | `inferable` | inference | Fall back to whole-file scanning — backward-compatible with the 11 existing bats tests, which construct minimal plans with no Build Progress section. Deleting that fallback would break the existing suite without delivering value. |
| Behavior when slice has no `**Files:**` line | `inferable` | inference | Fall back to the existing substring matcher — backward-compatible with existing tests (3.2a constructs a plan with no Files declaration). The new file-path path covers the new code; the fallback path covers the legacy. |
| Branch base for file-path matcher | `inferable` | inference | Reuse `check_scope`'s `for branch in ("origin/main", ...)` resolution. Single source of truth for "what is trunk?" across the script. |
| `--pre-pr` behavior on AC checkboxes after the fix | `inferable` | inference | ACs are silently ignored by parse_plan — they are not steps. The gate becomes "all Build Progress steps `[x]`," which matches what the gate's name implies. The pre-merge contract is that the build is done, not that every aspirational AC has been re-checked at gate time. |
| Plan-format contract change | `inferable` | inference | None required. `**Files:** \`a\`, \`b\`` is already what `/plan` emits per-slice; the matcher just consumes it. No new plan-format rules invented. |
| Where new bats tests live | `inferable` | inference | Same file as existing tests (`tests/scripts/progress_guardian_tests.bats`), new section "Step 4 — Issue #525 regressions" with three subsections (4.1 origin-main preference, 4.2 file-path matcher, 4.3 Build Progress anchor). Co-located coverage; no fixture sprawl. |

No `LOW_VALUE` items.

## Consistency Gate

- [x] Intent is unambiguous — *Three independent bugs in `scripts/progress_guardian.py`; fix each with the minimum-blast-radius implementation chosen in the approach contract; preserve all existing exit codes, JSON shape, and 11 passing bats tests.*
- [x] Every behavior/goal maps to an acceptance criterion — A1 (Change 1: stale main), A2 (Change 2: commit matcher), A3 (Change 3: parse_plan anchor), A3b (Change 4: AC mirror skip), A4 (real-world repro), A5 (no regressions), A6 (CI).
- [x] Architecture constrains without over-engineering — one file edited, no new modules, no helper extraction, no API changes, three surgical fixes.
- [x] Terminology consistent across artifacts — *Build Progress*, *Acceptance Criteria*, *file-path matcher*, *substring fallback*, *origin/main preference* used identically.
- [x] No contradictions between artifacts — the three locked decisions and the four `inferable` decisions appear identically in Intent, Architecture, Acceptance, and Ambiguity Log.
- [x] Every gap/ambiguity finding is logged — nine findings, three resolved by human, six inferable with explicit rationale, zero undocumented assumptions, zero `LOW_VALUE`.

**Verdict: PASS.** Ready for `/plan`.
