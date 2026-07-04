# 14. Python for cross-OS scripts

Date: 2026-07-02

## Status

Accepted, superseded by [ADR 0015](0015-bash-removal-complete.md) for the shipped-script surface (the bash → Python migration completed with epic #572).

## Context

The plugin declares cross-platform support in CLAUDE.md: shell scripts (both the dev/CI ones and the scripts shipped inside the plugin) must run on macOS, Linux, **and Windows**, where "Windows" means Git Bash — the POSIX shell Claude Code uses under Git for Windows. Until issue #567 we had no automated verification that any script actually worked on Windows; adding a `windows-latest` CI job in #570 immediately surfaced concrete friction that isn't fixable in bash:

- **Chocolatey has no `bats` package.** Bats-core has to be installed from an upstream tarball. Not a bash defect, but a test-tooling friction we now carry forever.
- **Chocolatey's `shellcheck` is stuck at v0.9.0.** New checks in v0.10+ trip Windows CI without being Windows-specific bugs. Installing shellcheck from upstream release binaries works, but again is friction we carry.
- **MSYS bash's fork emulation hangs `wait $!` in a common test-setup idiom.** Filed as #571. The `bash -c 'exit 0' & wait $!` pattern for obtaining a definitively-dead PID runs for six hours until GHA's job timeout kills it. No shell rewrite fixes this; only avoiding the pattern does.
- **`shasum` vs `sha256sum` vs Windows equivalents; `readlink -f` vs BSD `readlink`; `date +%N` vs BSD `date`; `IFS=`, empty-array expansion under bash 3.2, `set -e` propagation across command substitutions** — every helper we've written this year has needed careful multi-branch fork-per-platform code.

The wrapper's own logic **did** pass the Windows CI once the test-tooling infra was fixed (32/32 tests), so bash is not intrinsically broken on Windows. But the ecosystem *around* bash on Windows (test tooling, package management, MSYS quirks) compounds every new hook or test file. That friction is a permanent tax we don't want to pay per script.

Every plugin hook already declares `python3` as a hard dependency (see `mutation-gate.sh`, `cost-meter.sh`, `mutation-testing-smoke-gate.sh` — all of them have `command -v python3` guards at the top). So `python3` is a runtime the plugin already requires. Consolidating scripts on that runtime removes the bash-tooling friction as a class without adding new dependencies.

Design questions considered:

1. **All-or-nothing rewrite, or leave existing bash alone?** Rewriting all ~51 scripts in one PR is a 3-5 person-month exercise with real regression risk; every bug in the new Python is a bug that didn't exist before. Rejected in favor of **phased conversion behind an epic** (#572): new scripts in Python, existing bash converted one-by-one with a parallel-shipping cycle each.

2. **Which subset of Python?** Options:
   - **Full pip/virtualenv ecosystem.** Powerful but a friction bump for downstream .NET-repo operators copying scripts. Rejected.
   - **Stdlib-only.** Chosen. Every plugin hook and shipped script ships as a single file that runs under any `python3` ≥ 3.8. No `requirements.txt`, no virtualenvs, no pip.

3. **Minimum Python version.** Python 3.8 is what the plugin's other python scripts already target (`scripts/session_extract.py`, `hooks/lib/cost_meter.py`, `plugins/dev-team/hooks/mutation-adapters/lib.sh`'s python3 shells). 3.8 is EOL upstream, but is the floor most operating systems still support (Ubuntu 20.04 LTS, macOS Homebrew, Windows Python.org). Chosen.

4. **Are shell hooks with a JSON stdin/exit-code contract portable to Python?** Yes — Claude Code hooks are invoked as `bash hooks/foo.sh` (see `settings.json`), which we change to `python3 hooks/foo.py` per hook as it converts. The stdin JSON payload and exit-code semantics are identical.

5. **Startup latency.** Python's interpreter startup is ~30-100ms cold. Bash starts in <10ms. On a busy Claude Code session with N hooks firing per Bash tool call, that adds ~500ms of overhead. Acceptable given the alternative is script bugs that surface only on Windows CI. Instrumentation via the cost-meter will surface any real regression.

## Decision

**All new scripts in this plugin (shipped hooks, dev/CI helpers, and user-invocable shipped tooling) are authored in Python 3.8+ using stdlib only.** Existing bash scripts stay in place until converted; conversions land as part of the phased plan in #572 (bash → Python migration epic).

Concretely:

- **New scripts land as `.py`.** No new `.sh` files enter `plugins/dev-team/` after this ADR (exception: the two-line install trampolines that must be shell — the plugin's `install.sh` is not being rewritten).
- **Existing `.sh` scripts** remain functional and supported until #572's phased conversion reaches them. When a bash script gets a substantive change, prefer converting it to Python in the same PR over patching bash.
- **Test infrastructure follows the same rule.** New pytest for new Python scripts; existing bats stays until the shipped script it tests converts.
- **The bash 3.2 / macOS + Linux + Windows Git Bash portability rules in CLAUDE.md remain in force** for all existing bash. Once #572 completes, those rules retire.

Enforcement: an audit script (`scripts/check-python-only.py`) flags any new `.sh`/`.bats` file added repo-wide (outside an explicit allowlist) in a PR diff, wired into both `scripts/ci-local.sh` (pre-push) and CI (`.github/workflows/plugin-tests.yml`). Blocking by default as of issue #702, now that the epic's Phase 3 gate (ADR 0015) has landed — see [`docs/enforce-prefer-python-over-bash.md`](../enforce-prefer-python-over-bash.md) for the mechanism design and allowlist rationale.

## Consequences

- **Cross-platform behavior converges on one runtime.** Python stdlib's `subprocess`, `signal`, `pathlib`, `json`, `hashlib`, `argparse` behave identically on macOS, Linux, Windows Git Bash, and native Windows. Every script we author now works everywhere without per-platform forks.
- **The MSYS class of bug goes away for new scripts.** #571 (fork-hang in bash setup) doesn't reappear.
- **CI infrastructure simplifies.** Once bash conversion is complete, `bats`, `shellcheck`, and the Windows Git Bash CI job get retired. Existing Linux CI keeps running for the transition period.
- **The plugin still requires `python3` — no new dep.** Every hook already checks for it. Documented as ≥ 3.8 baseline.
- **Downstream .NET consumers who copy shipped scripts** now copy `.py` files. Migration story: one file (`csharp_stryker_net_wrapper.py`) or two (`+ csharp_stryker_net_status_loop.py`), same as bash was.
- **~30-100ms per-hook startup overhead** on cold-cache Python. Instrumented via `cost-meter.sh`'s telemetry; if aggregate hook time regresses meaningfully, the epic's Phase 2 revisits.
- **Existing bash scripts continue to work** during the transition; nothing regresses. The rule only constrains *new* scripts.
- **Contributors need Python 3.8+ locally.** Already required by the current plugin's test suite; not a new burden.

## Alternatives considered

- **Rewrite all 51 bash scripts in one PR.** Rejected: 3-5 person-month scope, real regression risk, contradicts the plugin's "small PRs" convention. #572 breaks it into phases.
- **Keep bash + require MSYS discipline in reviews.** Rejected: the discipline is unenforceable across every new hook/script, and #571-class bugs still slip through. This is the state we were in before this ADR.
- **Rewrite in Rust or Go.** Powerful, but adds a compile step, a binary distribution story, and a per-platform release matrix. Python's tradeoff (stdlib runtime, no compile) is materially cheaper for the plugin's needs.
- **Rewrite in JavaScript/Node.** Node is not already required by every hook (Python is), and adds a `node_modules` story. Rejected.
- **Selective: only shipped scripts, not internal hooks.** Considered. Rejected because the highest-friction files (`mutation-gate.sh`, `cost-meter.sh`, `telemetry.sh`) are internal hooks — leaving them in bash preserves most of the platform tax.

## References

- **Epic**: #572 (bash → Python migration for plugins/dev-team) — phased conversion plan
- **Motivating incident**: #567 (Windows Git Bash verification), #571 (MSYS setup() fork hang)
- **First conversion (Phase 1)**: PR #573 (csharp-stryker-net-wrapper + status-loop → Python)
- **Related rules**: CLAUDE.md — new working-rule sections referencing this ADR
- **Memory**: `feedback_all_scripts_platform_neutral` — the rule-level implementation this ADR formalizes
