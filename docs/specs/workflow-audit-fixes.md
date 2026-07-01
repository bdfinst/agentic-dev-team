<!-- spec-version: 1 -->
# Spec: rename Tests/Eval workflows, route eval structural-gate through ci-local.sh

**Format:** dev-team specs v1
**Issue:** <https://github.com/bdfinst/agentic-dev-team/issues/531>

## Intent Description

The GitHub Actions PR-checks page groups by workflow name, but two of the biggest workflows (`.github/workflows/plugin-tests.yml` and `.github/workflows/agent-eval.yml`) name themselves `Tests` and `Eval` — labels so generic they give a failing-check reader no signal about which file to open. When any check under those workflows fails, discovering the source file requires knowing an out-of-band mapping. A second, less visible issue in the same workflow family: `agent-eval.yml`'s `structural-gate` job inlines commands that `scripts/ci-local.sh` already exposes as `chk_eval_corpus` and `chk_citation_lint`. That inline duplication means a rename of `scripts/eval_grade.py` (or a change to its flags) would break the CI gate without breaking the local gate — the two surfaces can drift silently.

This change makes three fixes that improve discoverability and remove one real drift risk, with zero behavioral impact on what runs:

1. Rename `plugin-tests.yml`'s `name:` from `Tests` to `Plugin tests`.
2. Rename `agent-eval.yml`'s `name:` from `Eval` to `Agent eval`.
3. In `agent-eval.yml`'s `structural-gate` job, replace the two direct command invocations (`python3 scripts/eval_grade.py --check-corpus` and `python3 scripts/citation_lint.py --all`) with `bash scripts/ci-local.sh --only=chk_eval_corpus` and `--only=chk_citation_lint` — matching the delegation pattern `plugin-tests.yml` already uses.
4. Add a one-paragraph comment near the top of `link-check.yml` documenting the intentional local/CI split for `chk_nav_integrity` (local version is the fast subset; CI version adds `mkdocs build` + `lychee` to keep those tools off the local prereq list).

## Architecture Specification

**Files edited (four):**

- `.github/workflows/plugin-tests.yml` — one-token rename on line 1 (`name: Tests` → `name: Plugin tests`).
- `.github/workflows/agent-eval.yml` — one-token rename on line 1 (`name: Eval` → `name: Agent eval`); replace the "Eval corpus integrity check" step and the "Citation drift lint (advisory)" step in the `structural-gate` job with `bash scripts/ci-local.sh --only=<check>` invocations.
- `.github/workflows/link-check.yml` — add a comment block near the top documenting the local/CI split relative to `chk_nav_integrity` in `scripts/ci-local.sh`.
- No other files.

**Public surface preserved:**

- **Job names** are unchanged. Branch protection rules match on job name, not workflow name. The four PR checks that exist today (`Eval corpus & graders`, `Eval corpus semver`, `Eval live regression (opt-in)`, `Eval integration tier (opt-in)`, `Plugin content & hooks`, `Shell scripts & suite`, `Cost regression`, `Semgrep rule fixtures`, `Red-team harness smoke`) continue to exist with those exact names.
- **Trigger events** are unchanged (`push`, `pull_request`).
- **Job order and dependencies** are unchanged.
- **The set of commands each job runs** is functionally unchanged: `--only=chk_eval_corpus` runs exactly `python3 scripts/eval_grade.py --check-corpus` (line 154 of ci-local.sh); `--only=chk_citation_lint` runs exactly `python3 scripts/citation_lint.py --all` (line 156). Same commands, one indirection layer.

**Explicit non-changes (rejected before spec-writing):**

- The `structural-gate`'s explicit `bats tests/repo/eval_grader_tests.bats ...` step (four bats files) is **left inline**. Migrating it to `--only=chk_bats_repo` would broaden the CI job to run all of `tests/repo/`, which `plugin-tests.yml`'s `bats-tests` job (Plugin content & hooks) already does — introducing a duplicate run per PR. This spec's fix removes drift risk; it doesn't consolidate everything.
- **Apt-cache block deduplication** across four jobs → deferred to a separate PR (would require extracting a composite action; new file surface).
- **Adding `chk_eslint` to `pr-title-lint.yml`** → deferred (audit-suggested but out of the rename scope; policy call on whether npm's eslint should gate PR titles).
- **Adding `chk_oe_staleness` to any CI job** → deferred (policy question on whether local-only checks should promote to CI).

**Risk surface:**

- **Branch protection compatibility.** The rename risks nothing because branch protection matches on job names, not workflow names. Job names are untouched. Verified during spec-writing by inspecting `agent-eval.yml` lines 82-90: each job explicitly documents "Job name is a REQUIRED status-check context ... Keep it paren-free and issue-number-free" — the workflow authors already understood this distinction.
- **Actions tab lookup by workflow name.** External integrations (dashboards, log-searches) that filter by workflow name will see the new labels. This repo has no such known integration. Verified by grepping for `workflow: Tests` and `workflow: Eval` — no other file references them.
- **Cache invalidation.** The apt-cache keys use `${{ hashFiles('**/*.yml') }}` which will change when the workflow files are edited — one cache miss on first run after merge, no ongoing impact.

## Acceptance Criteria

Each criterion is a deterministic check.

**A1 — `plugin-tests.yml` renamed.**
`grep -c '^name: Plugin tests$' .github/workflows/plugin-tests.yml` returns exactly `1`; `grep -c '^name: Tests$' .github/workflows/plugin-tests.yml` returns exactly `0`.

**A2 — `agent-eval.yml` renamed.**
`grep -c '^name: Agent eval$' .github/workflows/agent-eval.yml` returns exactly `1`; `grep -c '^name: Eval$' .github/workflows/agent-eval.yml` returns exactly `0`.

**A3 — `agent-eval.yml`'s structural-gate delegates two checks through `ci-local.sh --only`.**
Within the `structural-gate` job's steps, there is exactly one step whose `run:` contains `--only=chk_eval_corpus` and one whose `run:` contains `--only=chk_citation_lint`. There is zero remaining occurrence of `scripts/eval_grade.py --check-corpus` or `scripts/citation_lint.py --all` as direct commands within that job. The bats-specific step (running `eval_grader_tests.bats` and friends) is preserved unchanged.

**A4 — `link-check.yml` documents the local/CI split.**
`.github/workflows/link-check.yml` contains a comment block (any placement above the `jobs:` line) that: (a) names `chk_nav_integrity` in `scripts/ci-local.sh`; (b) states that this workflow is a superset that additionally runs `mkdocs build` and `lychee`; (c) states that those tools intentionally stay CI-only. Verified by grep: `grep -c 'chk_nav_integrity' .github/workflows/link-check.yml` ≥ 1 AND `grep -c 'mkdocs' .github/workflows/link-check.yml` ≥ 1 AND `grep -c 'lychee' .github/workflows/link-check.yml` ≥ 1.

**A5 — Job names, triggers, and dependencies unchanged.**
Diff verification: `git diff origin/main..HEAD -- .github/workflows/*.yml | grep -E '^-\s*name:' | grep -Ev '^-name: Tests|-name: Eval'` returns empty (no job name touched other than the two workflow-level renames). `git diff origin/main..HEAD -- .github/workflows/*.yml | grep -E '^[+-]\s*(push:|pull_request:|workflow_dispatch:)'` returns empty (no trigger touched).

**A6 — Local dry-run of the two migrated commands.**
`bash scripts/ci-local.sh --only=chk_eval_corpus,chk_citation_lint` exits 0 (or the same status the current inline commands produce today, verified against `python3 scripts/eval_grade.py --check-corpus; python3 scripts/citation_lint.py --all`). This proves the delegation runs the same commands with the same exit semantics.

**A7 — CI/release hygiene.**

- `bash scripts/ci-local.sh` exits 0 (full local gate green).
- PR title prefix `chore(ci):` — matches release-please's non-shipping convention (no user-visible behavior change, workflow-only touches).
- PR opened with `--no-auto-merge` per CLAUDE.md (touches `.github/workflows/`).
- On the PR checks page after merge: `Plugin tests / Plugin content & hooks` and `Agent eval / Eval corpus & graders` appear as PR checks (manual verification, screenshot in PR body).

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| Which structural-gate steps to migrate to `--only` | `requires-stakeholder-input`, resolved at spec-write time | inference from ci-local.sh grep | Only `chk_eval_corpus` and `chk_citation_lint` — those are the two ci-local functions with an exact 1:1 command match. The bats-list step (4 specific files) has no matching helper; migrating it would double-run the whole `tests/repo/` dir. |
| Workflow renames — should we also touch job names? | `inferable` | inference | No. Job names are branch-protection contexts. Touching them would require updating branch protection rules externally, which is out of scope. Issue #531 also explicitly says "Job names are unchanged (they're what branch protection matches on)." |
| Comment format in `link-check.yml` | `inferable` | inference | YAML `#`-prefixed comment block above `jobs:`. Matches the comment style already used in `agent-eval.yml` (lines 82-90) and `pr-title-lint.yml`. No new format invented. |
| PR title convention (`chore(ci):` vs `refactor(ci):` vs `feat(ci):`) | `inferable` | inference | `chore(ci):` — this is workflow-config maintenance with no user-visible behavior change and no functional change to the checks CI runs. release-please treats `chore:` as no-version-bump, which is correct: neither the plugin ships nor changes. |
| Whether to remove the workflow-name literal from job body-comment references | `inferable` | inference | No changes to internal comments referencing the old names (if any exist) — spec is bounded to the four surfaces named in Architecture Specification. A grep-cleanup could be done in a follow-up if drift becomes visible. |
| Add-eslint-to-CI and apt-cache-extraction | `requires-stakeholder-input`, resolved by user in issue #531 body | issue #531 out-of-scope section | Both parked for future PRs. Not touching them. |

No `LOW_VALUE` items.

## Consistency Gate

- [x] Intent is unambiguous — *rename two workflow names for discoverability, route two commands through `ci-local.sh --only` for consistency with `plugin-tests.yml`'s existing pattern, add a comment to `link-check.yml` explaining a documented split. Zero behavioral change to what CI runs.*
- [x] Every behavior/goal maps to an acceptance criterion — A1 (rename plugin-tests), A2 (rename agent-eval), A3 (delegate structural-gate), A4 (document local/CI split), A5 (no other diff), A6 (local dry-run), A7 (CI + PR hygiene).
- [x] Architecture constrains without over-engineering — four files edited, no new files, no new abstractions, only the changes issue #531 called out with the out-of-scope items explicitly excluded.
- [x] Terminology consistent across artifacts — *rename*, *delegate*, *local/CI split*, *branch protection matches job names* used identically.
- [x] No contradictions between artifacts — the four decisions and their rationales appear identically in Intent, Architecture, and Ambiguity Log.
- [x] Every gap/ambiguity finding is logged — six findings, two resolved by human via issue text, four inferable with explicit rationale.

**Verdict: PASS.** Ready for `/plan`.
