# 15. Bash removal complete — plugins/dev-team is Python-native

Date: 2026-07-02

## Status

Accepted. Supersedes the transition-era clauses of [ADR 0014](0014-python-for-cross-os-scripts.md) for the `plugins/dev-team/` surface.

## Context

[ADR 0014](0014-python-for-cross-os-scripts.md) committed to a phased bash → Python migration under epic #572 (44 sub-issues). The transition-era rules ("new scripts land as .py, existing .sh stay until converted") were the price of shipping incrementally without breakage. That transition is now complete: every hook, script, hook-lib, and mutation adapter under `plugins/dev-team/` has been ported to Python 3.8+ stdlib and validated against a byte-equal parity harness across ~220 fixture cases spanning happy paths, empty stdin, malformed input, and Windows-path fixtures.

The parity harness's job is now over — the `.sh` implementations it dispatched against have been deleted. The comparative-testing gate that protected each slice merge is now dead weight and retires with the `.sh` files. Going forward, the plugin's `test_*.py` unit tests are the coverage source of truth.

## Decision

1. **Every shipped script under `plugins/dev-team/` is Python 3.8+ stdlib-only.** The single exception is `plugins/dev-team/install.sh` — a two-line trampoline that detects the shell environment (needed so we can tell users to install Git Bash on Windows *before* running Python).

2. **The `sh -c 'if [ "${DEV_TEAM_PY_HOOK_*:-0}" = "1" ]; then python3 …; else bash …; fi'` toggle wrapper is retired** from `plugins/dev-team/settings.json`. Every hook invocation is now a plain `python3 hooks/<name>.py`. Operators no longer need to opt into Python via env var.

3. **The `plugins/dev-team/tests/hooks/parity/` harness is retired.** The going-forward coverage lives at `plugins/dev-team/tests/hooks/test_*.py` (~23 pytest files, 220+ assertions) and `plugins/dev-team/tests/scripts/test_*.py` (2 files).

4. **`shellcheck` is retained** as a repo-wide dev prerequisite because `plugins/security-assessment/` and repo-root `scripts/*.sh` still exist. It is no longer required for `plugins/dev-team/` itself.

5. **`bats-core` is retained** as a repo-wide dev prerequisite because ~130 markdown-reference / registry-drift / knowledge-schema / agent-frontmatter / cost-regression / eval-grader / semgrep-fixture / skill-doc content-guards under `tests/{repo,skills,agents,knowledge,commands,docs,bats,lib}/` are still bats. These test the repository's markdown/JSON/frontmatter integrity — not the bash-vs-Python question — and have no pytest equivalent yet. Their migration is tracked in a follow-up epic. The `Hermetic bats fixtures` rule in the top-level CLAUDE.md stays in force for those files.

6. **Windows CI is now fully bash-free for the plugin.** `.github/workflows/wrapper-windows.yml` already runs Python-only. Nothing in the `plugins/dev-team/` runtime requires Git Bash on Windows anymore.

## Consequences

- **Downstream .NET operators must migrate to `.py`.** This was communicated as a breaking change in the (unreleased) v9.0.0 changelog and in `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md`.

- **No hook-startup latency regression observed** in the parity fixtures. If a subsequent perf gate flags Python cold-start on Windows, the mitigation is to merge related hooks into one dispatcher (per ADR 0014's Risk section), not to reintroduce bash.

- **The bash 3.2 / GNU-flag / Git Bash portability section of `CLAUDE.md` is deleted.** It was scaffolding for the transition; it has nothing to enforce anymore. If a repo-root script (`scripts/*.sh`) hits macOS-vs-Linux friction, that's now a signal to convert THAT script to Python opportunistically — not to reintroduce a portability-rules section.

- **The `feedback_all_scripts_platform_neutral` memory rule is rewritten** from "every shell script must run on macOS + Linux + Windows Git Bash" to "every shipped Python script probes OS-specific paths rather than hard-coding them." The underlying intent (no silent platform-specific failures) is preserved; the enforcement mechanism moved from portable-bash to stdlib-only-Python.

## Non-goals

- **Not migrating the ~130 content-guard bats to pytest** in this PR. That's a separate, orthogonal effort (test tooling only, no plugin runtime change).
- **Not touching `plugins/security-assessment/` scripts** — different plugin, different owner, out of scope for #572. Concretely, this is why `plugins/dev-team/hooks/*.py` and `plugins/security-assessment/hooks/*.sh` use different hook file-naming conventions today: the divergence is this ADR's stated scope boundary, not an inconsistency to fix.
- **Not migrating repo-root `scripts/*.sh`** (`ci-local.sh`, `dev-setup.sh`, `cost-regression-check.sh`, `assemble-docs.sh`, `run-full-eval.sh`, ...). These orchestrate developer tooling AROUND the plugin, not the plugin itself, and are not shipped downstream. Convert opportunistically when touched.
