<!-- spec-version: 8.3.4 -->
# Spec: Pre-push hook hermetic fixtures (issue #546)

## Intent Description

The pre-push hook (`.husky/pre-push` → `scripts/ci-local.sh`) currently corrupts local branch refs — including `main` — during real `git push` invocations, silently rewriting them to a chain of fixture-repo commits authored `Test <test@test.com>`. The corruption does not reproduce when the hook is invoked directly with the same stdin. Root cause: git exports `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_WORK_TREE`, `GIT_PREFIX`, and `GIT_REFLOG_ACTION` into the pre-push hook's environment; nothing in the hook chain scrubs them; fixture bats tests that run `git init`/`git commit`/`git push` inherit those env vars and target the parent worktree's gitdir instead of their tempdirs.

This spec fixes the corruption at three layers of defense: hermetic isolation in every fixture bats `setup()` (via a shared helper), the same env-scrub at the top of `scripts/ci-local.sh`, and a post-hook ref-integrity guard in `.husky/pre-push` that refuses to complete if any local ref moved during the hook run. It also standardizes fixture tempdirs on a per-worker prefix and adds a PWD-guard so any future drift fails a test instead of clobbering a worktree.

The outcome: `git push` on this repo never mutates local refs as a side effect of hook execution, regardless of parallel bats scheduling, fixture bugs, or future env inheritance surprises. The relative `hooksPath` in the shared bare repo is out of scope — env-scrub alone closes the corruption channel; changing shared bare config is a separate concern.

## Architecture Specification

**Components touched:**

- `tests/lib/hermetic.bash` — **new.** Shared bats helper. Exports a single function (e.g. `hermetic_setup`) that: (a) `unset`s `GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_REFLOG_ACTION`; (b) exports `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null`; (c) creates a per-worker tempdir via `mktemp -d -t "bats-$$-XXXX"` and cds into it; (d) installs a `DEBUG`/`RETURN` trap that fails the test if `PWD` ever leaves the tempdir root. Bash-3.2 safe (macOS).
- `scripts/ci-local.sh` — add env-scrub as the first executable lines, before the existing `cd "$(git rev-parse --show-toplevel)"`. `unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_REFLOG_ACTION`. Do not set `GIT_CONFIG_GLOBAL=/dev/null` here — ci-local reads real repo state; only the bats fixtures need config isolation.
- `.husky/pre-push` — capture `git for-each-ref refs/heads/` before invoking `ci-local.sh`, and re-read it after. On mismatch, abort with a loud diagnostic naming the changed refs and their pre/post SHAs. This runs even when `ci-local.sh` exits zero.
- Fixture bats files under `tests/scripts/` and `tests/repo/` (and any other `.bats` file that calls `git init`/`git commit`/`git push` in `setup()`) — source `tests/lib/hermetic.bash` and call `hermetic_setup` at the top of `setup()`, replacing the ad-hoc `mktemp -d` + `cd` pattern. Existing `|| return 1` cd guards can stay (harmless) or be removed as the shared helper's PWD trap subsumes them.

**Constraints:**

- Bash 3.2 compatible (macOS ships 3.2): no `mapfile`, no `declare -A`, no `wait -n`, empty-safe array expansion.
- Cross-platform: macOS, Linux, Windows Git Bash. `mktemp -d -t "PREFIX-XXXX"` works on all three (macOS puts prefix in name, Linux/Git Bash accept `-t`).
- The shared bare repo's `hooksPath = .husky/_` is **not** modified. This spec closes the corruption channel; the relative-hooksPath amplifier is a separate concern.
- The new post-hook ref guard in `.husky/pre-push` must not itself corrupt refs — it only reads via `git for-each-ref` and compares strings.
- Fixture bats tests that legitimately need `git push` to a fixture-local `origin` continue to work — env scrubbing does not remove the fixture's own git operations, only prevents them from finding a parent gitdir.
- All existing bats tests continue to pass on `bash scripts/ci-local.sh` (direct invocation) and under `git push` (hook invocation).

**Dependencies:** No new runtime dependencies. Uses only bash builtins, `mktemp`, `git for-each-ref`, and standard test tooling already required.

## Acceptance Criteria

1. Running `git push` on any branch in this repo (with the pre-push hook active) leaves every ref under `refs/heads/*` unchanged from its pre-hook value — regardless of whether `ci-local.sh` passes or fails.
2. Given a hostile environment (`GIT_DIR=<decoy-gitdir> GIT_INDEX_FILE=<decoy-index>`), invoking `bash scripts/ci-local.sh` does not mutate the decoy gitdir's refs, and its child bats processes see empty `GIT_DIR`/`GIT_INDEX_FILE`/`GIT_WORK_TREE`/`GIT_PREFIX`/`GIT_REFLOG_ACTION`.
3. Given a hostile environment (same decoy vars), invoking any fixture bats test's `setup()` (via `hermetic_setup`) does not mutate the decoy gitdir's refs, and the fixture's git operations target only its own tempdir.
4. If a fixture bats test's `PWD` ever leaves the per-worker tempdir root created by `hermetic_setup`, the test fails loudly with a diagnostic naming the drift — never silently proceeds.
5. If any ref under `refs/heads/*` changes during `.husky/pre-push` execution, the hook exits non-zero with a diagnostic listing every changed ref, its pre-hook SHA, and its post-hook SHA — even if `ci-local.sh` itself exits zero.
6. Two fixture bats tests running concurrently (`bats --jobs 2` or `run-bats-parallel.sh -j 2`) each get a distinct tempdir root; neither can observe or mutate the other's fixture.
7. `bash scripts/ci-local.sh` (direct invocation, no hook) continues to pass on a clean tree.
8. Running the full test suite under a real `git push` on a scratch branch completes without corrupting any local ref on any worktree of the shared bare repo.
9. All acceptance criteria are enforced by automated tests that fail without the fix and pass with it.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| Fix scope (root-cause only vs. full 4-step + REFACTOR) | `requires-stakeholder-input` | human | "Full 4-step plan + REFACTOR" — env-scrub in fixtures + ci-local.sh + post-hook ref guard + per-worker tempdirs + shared hermetic helper |
| Whether to change shared bare repo's `hooksPath = .husky/_` to absolute | `requires-stakeholder-input` | human | "Leave as-is" — env-scrub closes the corruption channel; hooksPath is a compounding factor, not root cause, and changing it touches config outside the checkout |
| Which env vars to scrub | `inferable` | inference | Triage investigation identified `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_WORK_TREE`, `GIT_PREFIX`, `GIT_REFLOG_ACTION` as git-exported; `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_SYSTEM=/dev/null` isolate global config. Standard git-hermeticity pattern |
| Whether ci-local.sh scrubs `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` | `inferable` | inference | No — ci-local.sh reads real repo state and may need real config (e.g. user.email for signed commits). Only the bats fixtures need config isolation |
| Which refs the post-hook guard checks | `inferable` | inference | All `refs/heads/*` via `git for-each-ref` — cheap, comprehensive, avoids false-negatives if corruption hits a ref other than the pushing branch (issue #546 explicitly notes `main` also gets clobbered) |
| Whether the post-hook guard runs when ci-local.sh exits non-zero | `inferable` | inference | Yes — corruption in #546 is silent regardless of ci-local exit code. Guard runs unconditionally |
| Location of the shared helper | `inferable` | inference | `tests/lib/hermetic.bash` per triage record; matches bats convention (`load '../lib/hermetic'`) |
| Whether existing `|| return 1` cd guards from PR #545 must be removed | `inferable` | inference | No — they are harmless once the shared helper's PWD trap is in place. Removal is a follow-up cleanup, not part of this fix |
| Tempdir prefix format | `inferable` | inference | `mktemp -d -t "bats-$$-XXXX"` — `$$` gives per-worker namespace (bats PID), `XXXX` is mktemp's own randomness. Cross-platform (macOS, Linux, Git Bash) |
| Whether to file separately the observation that `hooksPath` is relative | `inferable` | inference (LOW_VALUE for this spec) | Note in code review but out of scope here; env-scrub alone satisfies acceptance criteria |

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret it the same way (scrub env, add guard, add per-worker tempdirs, extract shared helper; leave hooksPath alone)
- [x] Every behavior/goal maps to an acceptance criterion (AC1 = intent's "never mutates refs"; AC2/3 = env-scrub in ci-local + fixtures; AC4 = PWD guard; AC5 = post-hook guard; AC6 = per-worker tempdirs; AC7 = direct invocation still works; AC8 = end-to-end; AC9 = tests enforce all of the above)
- [x] Architecture constrains without over-engineering (one new helper file, edits to two hook/script files, sourcing the helper from existing bats files; no new dependencies, no shared-bare-repo config changes)
- [x] Terminology consistent across artifacts (hermetic, env-scrub, per-worker tempdir, post-hook ref guard, shared helper)
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — two `requires-stakeholder-input` items resolved by human via /ship, the rest classified `inferable` with explicit rationale

**Verdict: PASS.**
