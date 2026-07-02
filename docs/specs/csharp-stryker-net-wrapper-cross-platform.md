<!-- spec-version: 1 -->
# Spec: csharp-stryker-net-wrapper.sh Cross-Platform DOTNET_ROOT Probe (issue #564)

## Intent Description

The wrapper shipped in PR #563 (closing #559) declares itself macOS/Linux-only and hard-codes a Homebrew macOS `DOTNET_ROOT` fallback (`/opt/homebrew/opt/dotnet/libexec`). This contradicts the plugin's stated cross-platform requirement (CLAUDE.md: "Windows = Git Bash"; hooks and helper scripts must run under Git Bash on Windows) and creates two silent-failure paths for consumers: Linux operators whose `DOTNET_ROOT` isn't pre-set get an opaque Stryker.NET runtime error rather than the wrapper's own error message, and Windows Git Bash operators can't use the wrapper at all because the shipped default is wrong for their platform.

This change replaces the hard-coded fallback with a **probe** that walks each platform's standard .NET install locations, then falls back to `dirname $(command -v dotnet)`, then exits with a specific error code and actionable message if nothing resolves. The header comment drops the "Windows Git Bash not a supported target" line — the script must work on macOS, Linux, and Windows Git Bash without changes. No behavior change on macOS Homebrew installs (that path is the first probe candidate and continues to win).

Success is measured on three platforms: a fresh macOS Homebrew install continues to work with zero configuration; a Linux install with `dotnet` on `PATH` works with zero configuration; a Windows Git Bash install with `dotnet` in `/c/Program Files/dotnet` works with zero configuration; and an install with no `dotnet` anywhere exits with code 3 and a message telling the operator what to do.

## Architecture Specification

### Components affected

- `plugins/dev-team/skills/mutation-testing/scripts/csharp-stryker-net-wrapper.sh` — the DOTNET_ROOT export block and the header comment. No other file needs to change.
- `tests/skills/mutation_testing_wrapper_tests.bats` — extend with probe-order + no-SDK + partial-install coverage. Same fake-dotnet fixture pattern already established for the wrapper.

### Interfaces

- **DOTNET_ROOT probe order** (first match wins):
  1. `$DOTNET_ROOT` pre-set — never overwritten. (Existing behavior, preserved.)
  2. `/opt/homebrew/opt/dotnet/libexec` — macOS Apple Silicon Homebrew.
  3. `/usr/local/opt/dotnet/libexec` — macOS Intel Homebrew.
  4. `/usr/share/dotnet` — Debian/Ubuntu default (`apt install dotnet-sdk-*`).
  5. `/usr/lib/dotnet` — Fedora/RHEL default (`dnf install dotnet-sdk-*`).
  6. `$HOME/.dotnet` — user-scope install via `dotnet-install.sh`.
  7. `/c/Program Files/dotnet` — Windows Git Bash on 64-bit Windows.
  8. `/c/program files/dotnet` — Windows Git Bash on filesystem with lowercase drive mount.
  9. `$(dirname "$(command -v dotnet)")` — final fallback: dotnet on PATH implies its directory contains the runtime.
- A path counts as a hit when either `<candidate>/dotnet` is executable (`-x`) or `<candidate>/shared` is a directory (the SDK layout).
- **Exit contract when no SDK found**: exit code `3` (distinct from the existing exit `2` for stale-hidden-.sln refusal), message on stderr naming the paths probed and instructing the operator to either set `DOTNET_ROOT` explicitly or install .NET (link to <https://dotnet.microsoft.com/download>). Trap-restore is not triggered because the probe runs before the `.sln` hide operation.
- **Header comment** — replace the "macOS/Linux only" line with "Runs on macOS, Linux, and Windows Git Bash." No other prose change.
- **No new dependencies** — probe uses `[`, `command -v`, `dirname`, `[ -x ]`, `[ -d ]`; all bash 3.2-safe and POSIX-portable.

### Dependencies

- Must remain compatible with the existing wrapper contract (14 bats tests in `mutation_testing_wrapper_tests.bats` + 2 integration tests). No signature change to `restore_sln`, no reordering of the trap-restore / pre-build / hide sequence.
- Must remain compatible with the status-loop's assumptions (loop doesn't look at `DOTNET_ROOT`).

### Constraints

- **No behavior change on existing platforms.** macOS Homebrew installs continue to hit `/opt/homebrew/opt/dotnet/libexec` as the first probe candidate; no observable difference from today.
- **Fail fast, never silently.** A missing SDK exits with a specific code and message before any state mutation (`.sln` hide, `dotnet build` invocation).
- **Platform-neutral shell.** No `readlink -f`, `sed -i` semantics divergence, `date +%N`, or other GNU-only constructs in the probe block. Consistent with the existing script's bash 3.2-safe style.
- **`DOTNET_ROOT` pre-set is authoritative.** The probe only runs when the env var is unset — respects operator override.

## Acceptance Criteria

- [ ] Wrapper header comment states "Runs on macOS, Linux, and Windows Git Bash" (no "not a supported target" text for any platform).
- [ ] When `DOTNET_ROOT` is pre-set, the wrapper does not overwrite it. (Existing behavior; regression-guard.)
- [ ] When `DOTNET_ROOT` is unset and `/opt/homebrew/opt/dotnet/libexec/dotnet` is executable, the wrapper exports that path. (macOS Apple Silicon Homebrew — the current baseline.)
- [ ] When `DOTNET_ROOT` is unset and `/usr/share/dotnet/dotnet` is executable, the wrapper exports `/usr/share/dotnet`. (Debian/Ubuntu.)
- [ ] When `DOTNET_ROOT` is unset and `/c/Program Files/dotnet/dotnet.exe` OR `/c/Program Files/dotnet/shared` is present, the wrapper exports `/c/Program Files/dotnet`. (Windows Git Bash — path with a space.)
- [ ] When no standard install path resolves but `dotnet` is on `PATH`, the wrapper exports `dirname $(command -v dotnet)` as `DOTNET_ROOT`.
- [ ] When no standard install path resolves and `dotnet` is not on `PATH`, the wrapper exits with code **3** and a stderr message that (a) names at least one standard install path it probed, (b) instructs setting `DOTNET_ROOT` explicitly, and (c) links to `https://dotnet.microsoft.com/download`.
- [ ] Exit-3 path does **not** hide `.sln`, does **not** run `dotnet build`, and does **not** invoke `restore_sln` on a state that shouldn't be restored (nothing to undo — the wrapper hasn't mutated anything yet).
- [ ] Probe hit-order is stable and matches the documented sequence (Homebrew Apple Silicon → Homebrew Intel → Debian → Fedora → user-scope → Windows Program Files → Windows lowercase → PATH fallback).
- [ ] `shellcheck` clean on the modified wrapper.
- [ ] All existing 14 wrapper bats tests still pass.
- [ ] All existing 2 wrapper + loop integration tests still pass.
- [ ] All existing 14 status-loop unit tests still pass.
- [ ] New bats tests cover: pre-set-preserved (regression guard, already exists — verify still passes); each documented probe candidate hit path; PATH-fallback hit path; no-SDK exit 3 with actionable message; probe hit-order (higher-priority candidate wins when multiple present).
- [ ] Local gate (`scripts/ci-local.sh`) passes.
- [ ] PR title conventional (`fix(mutation-testing): probe DOTNET_ROOT across macOS + Linux + Windows Git Bash (#564)`).
- [ ] PR body uses `Closes #564`.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Behavior when no SDK found — exit fast or fall through? | `requires-stakeholder-input` | inference (user AFK; recommended default) | Exit 3 with actionable message. Fail-fast + specific error beats opaque `dotnet: command not found` downstream; also mirrors the wrapper's existing exit-2-on-refuse pattern. |
| Partial install (dotnet on PATH but no probe candidate hits) — fall back or fail? | `requires-stakeholder-input` | inference (user AFK; recommended default) | Fall back to `dirname $(command -v dotnet)`. Most install layouts colocate binary and runtime; refusing this path breaks the very "not on our documented list" install we want to support. |
| Which specific Linux paths to probe? | `inferable` | inference | Debian/Ubuntu `/usr/share/dotnet` and Fedora/RHEL `/usr/lib/dotnet` are the two documented Microsoft package layouts; user-scope `$HOME/.dotnet` covers `dotnet-install.sh` users. |
| Which specific Windows Git Bash paths to probe? | `inferable` | inference | `/c/Program Files/dotnet` is the Windows installer's default; the lowercase variant handles filesystem drive mounts on Git Bash configurations where case is preserved. Both are the entirety of what MS docs describe. |
| Exit code for no-SDK case — 3, 4, or 127? | `inferable` | inference | 3. Distinct from the existing 2 (stale-hidden-.sln refuse); reserved-in-conventional-shell range but not overloaded with a standard meaning (127 = "command not found," 126 = "not executable"). |
| Should we validate the probed path actually contains a working SDK (e.g., `dotnet --info` succeeds)? | `inferable` | inference | No. The probe checks structural markers (`-x dotnet` or `-d shared`); an actual SDK-execution check would be slow (~200-500ms) and inaccurate against dotnet SDKs vs runtimes. If the probed path is stale, `dotnet build` will fail with a real error; wrapper's job is finding the root, not diagnosing runtime state. |
| Should probe order be configurable via env var? | `inferable` | inference | No. Configuration surface adds cost without evidence of demand; operators who need something exotic can pre-set `DOTNET_ROOT`. If a future issue asks for it, add then. |
| Should the wrapper log which probe candidate won (for debugging)? | `inferable` | inference | No — silent success is the goal. Loud on failure (exit 3 names paths probed); quiet on success (no output). This matches operator expectation: the wrapper isn't verbose about its normal work. |
| Should the `dirname $(command -v dotnet)` fallback be gated on a minimum SDK version check? | `inferable` | inference | No. Version checking is Stryker.NET's job; a wrapper that gates on SDK version would need updating every time Stryker's requirements change. Fallback is unconditional — if dotnet is on PATH, use it. |
| Bats test strategy — same fake-dotnet fixture pattern? | `inferable` | inference | Yes. The existing wrapper tests use a fake `dotnet` shim on PATH; add probe-candidate directory fixtures under `$HERMETIC_ROOT` and cover each hit path by moving fake-dotnet binaries into place. |
| PR title convention (fix vs. feat)? | `inferable` | inference | `fix` — this corrects a defect in the shipped wrapper (opts a supported platform out), not adds new capability. |

## Consistency Gate

- [x] Intent is unambiguous — replace a hard-coded macOS-only fallback with a cross-platform probe; no observable behavior change on the currently-working path.
- [x] Every behavior/goal maps to an acceptance criterion (probe order → 9 criteria covering each candidate; no-SDK → exit-3 criterion; header → header-comment criterion; regression → existing-tests-still-pass criteria).
- [x] Architecture constrains implementation — probe order fixed, exit contract fixed, no new dependencies, no signature changes to existing functions.
- [x] Terminology consistent — "probe", "candidate", "DOTNET_ROOT", "SDK" used identically across all three sections.
- [x] No contradictions between artifacts — Intent's cross-platform goal, Architecture's probe order, and Acceptance's exit-3 semantics all agree.
- [x] Every gap/ambiguity finding is logged — two `requires-stakeholder-input` items marked (with the AFK-inference caveat), nine `inferable` items documented.

**Verdict: PASS.** Ready for `/plan`.
