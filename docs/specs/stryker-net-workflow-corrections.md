<!-- spec-version: 1 -->
# Spec: Stryker.NET Workflow Corrections (issue #522)

**Format:** dev-team `/specs` v1

## Intent Description

Several concrete instructions in the mutation-testing skill's C# / Stryker.NET reference are wrong or misleading for Stryker.NET 4.x and cause real failures — silent per-test coverage fallback on xunit.v3 test projects (masking mutants as timeouts), broken runs on macOS Homebrew installs (missing `DOTNET_ROOT`), a mislabeled `--report-file-name` flag, a `-V trace` probe that generates 1.5M+ log lines, a non-existent `--dry-run` flag, unknown-key JSON that hard-fails the run, and stale binaries producing phantom timeouts because no `dotnet build` precedes timing.

The change corrects the Stryker.NET language reference so a developer following it hits none of these traps. Scope is documentation-only: `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md`. No behavior change to the skill workflow, no changes to other language references, no code changes.

The PR body must include `Closes #522` so merging auto-closes the issue.

## Architecture Specification

**Files touched (single file):**

- `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md`

**Sections added or revised inside that file:**

1. **xunit.v3 detection block** — a new subsection before "Run (scoped)" that shows the `grep -rl "xunit.v3" tests/ --include="*.csproj"` detection, and prescribes: set `"coverage-analysis": "off"`, write `xunit.runner.json` with `"testTimeout": 5000`, add `<CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>` to the test csproj, set `additional-timeout: 30000`. Explains the "fake 100% score / all Timeout" failure mode.
2. **`DOTNET_ROOT` preamble** — every run command in the file exports `DOTNET_ROOT` with the Homebrew fallback path before invoking Stryker, and shows the `dotnet --info | grep "Base Path"` confirmation step. The path variable `STRYKER="${HOME}/.dotnet/tools/dotnet-stryker"` is used consistently.
3. **`-O` vs `report-file-name` clarification** — the file no longer shows `--report-file-name` as a CLI flag. A short note explains it is a **config-file key** that renames HTML/JSON output within the output directory; the CLI switch for output directory is `-O` / `--output`. Named runs use `-O StrykerOutput/<name>`.
4. **Probe verbosity** — probe commands drop `-V trace`. A `grep -E "Killed:|Survived:|Timeout:|mutation score"` extract is shown for summarizing any run regardless of verbosity. A note allows `-V trace` only when debugging startup problems.
5. **No `--dry-run`** — any reference to `--dry-run` is removed. (Verification step in Acceptance: `grep -c "dry-run"` on the file returns `0`.)
6. **Unknown-key warning** — a short paragraph noting that Stryker.NET rejects any unknown key in `stryker-config.json` since v1.x, and that JSON comment workarounds (`"_note"`, `"//"`) hard-fail the run. Document config intent in git commit messages or a nearby README instead.
7. **Pre-run `dotnet build`** — every timing/run block is preceded by `dotnet build <solution> -c Debug --nologo`, then `time dotnet test <test-project> -c Debug --no-build` for the baseline suite timing referenced in `SKILL.md` Step 1b.

**Constraints:**

- Language-agnostic content stays in `SKILL.md`; every correction lives in the C# reference file.
- No other language KB is touched; no code, agent, hook, or eval fixture changes.
- Existing shard-aware execution guidance for large repos is preserved and updated to include the `DOTNET_ROOT` preamble and `-O` output-directory pattern; commands remain runnable.
- Because this diff is markdown-only (touches only `*.md`), the working rule from the repo CLAUDE.md applies: arm auto-merge at PR-open time with `gh pr merge <num> --auto --squash`. `Closes #522` in the PR body auto-closes the issue on merge.

**Non-goals:**

- No refactor of `SKILL.md` workflow steps.
- No change to the JSON envelope, `--emit-json` schema, or workflow-callers registry.
- No install-time changes (nothing added to `init-dev-team` or `install.sh`).

## Acceptance Criteria

Every criterion is observable by grepping the changed file or running the referenced command.

1. **xunit.v3 detection block present.** `grep -c "xunit.v3" plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` returns ≥ 3 (detection command, coverage-analysis note, xunit.runner.json guidance). The block sets `"coverage-analysis": "off"`, creates `xunit.runner.json` with `"testTimeout": 5000`, adds `<CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>`, and sets `additional-timeout: 30000`.
2. **`DOTNET_ROOT` export appears in every run command.** All executable Stryker invocations in the file are preceded by `export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"`. The confirmation line `dotnet --info | grep "Base Path"` is present.
3. **Probe command uses default verbosity.** `grep -c -- "-V trace" plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` returns `0` for the probe command block. The file shows a `grep -E "Killed:|Survived:|Timeout:|mutation score"` summary extractor. One note may retain a mention of `-V trace` strictly labeled as "debug-only, not for probes"; if kept, it is a single occurrence outside a run command.
4. **`-O` used for output directory; `--report-file-name` documented as config key only.** Every named run uses `-O StrykerOutput/<name>`. `grep "report-file-name" plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` shows all occurrences inside a "config file key" explanation, never as a CLI flag in a command block.
5. **No `--dry-run` references remain.** `grep -c -- "--dry-run" plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` returns `0`.
6. **Unknown-config-key warning present.** The file contains a note that Stryker.NET rejects unknown keys in `stryker-config.json` since v1.x and that `"_note"` / `"//"` comment workarounds hard-fail the run.
7. **`dotnet build` precedes timing/run commands.** Each run/timing block includes `dotnet build ... -c Debug --nologo` before the `time dotnet test` or `dotnet stryker` invocation. Standalone snippets that show only a Stryker command reference the pre-build step in nearby prose.
8. **All existing shard-aware content still parses and runs.** Shard config discovery, `stryker-pipeline.py`, `stryker-setup.py`, and the "Finding the relevant shard config" bash helper remain in the file; the only additions are the seven corrections above.
9. **`/agent-audit` passes** on the modified file (no frontmatter, structural, or reference-link breakage).
10. **PR closes the issue on merge.** The PR body contains `Closes #522`. `gh pr view <num> --json body` shows the string. When the PR is merged, GitHub auto-closes issue #522.
11. **Documentation-only auto-merge armed.** At PR-open time, `gh pr merge <num> --auto --squash` is executed. The PR title uses a conventional-commit prefix (`docs(mutation-testing): correct Stryker.NET reference for xunit.v3, DOTNET_ROOT, CLI flags, verbosity`).

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Which file receives the seven corrections? The issue text says "Step 1 / tool-setup"; no `tool-setup` file exists. | `inferable` | inference | `grep -rn "tool-setup"` across the plugin returns no matching file. `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` is the sole Stryker.NET setup/run reference; every item in the issue maps directly onto its existing sections (install, run, timeout, notes). |
| Should `-V trace` be removed entirely, or kept as a debug-only note? | `inferable` | inference | Issue text says "Use `-V trace` only when actively debugging a startup problem" — a single labeled note is consistent with that intent; removing it entirely would drop useful escape-hatch guidance. |
| Where to put the unknown-config-key warning — the C# KB or `SKILL.md`? | `inferable` | inference | The behavior is Stryker.NET-specific (Stryker.NET 1.x+ rejects unknown keys; other tools differ). Belongs in the C# KB, not the language-agnostic `SKILL.md`. |
| Should xunit.v3 detection also be wired into `stryker-net.sh` mutation adapter (auto-detect at runtime)? | `requires-stakeholder-input` — deferred | inference (as scope decision) | Issue #522 asks only for documentation corrections. Auto-detection at adapter runtime is a behavior change; keeping this spec doc-only preserves the "documentation-only auto-merge" path and matches the issue's acceptance criteria. If the user wants adapter auto-detection, that is a separate issue and separate spec. |
| Should shard-aware examples also be revised to include the seven corrections (build pre-step, DOTNET_ROOT, -O)? | `inferable` | inference | Yes — the corrections are universal to Stryker.NET; leaving shard-aware examples uncorrected would recreate the same traps in the whole-repo path. Applying to every run block in the file. |
| PR auto-merge armed? | `inferable` | inference | Repo CLAUDE.md working rules explicitly state documentation-only PRs (touching only `*.md` and non-shipping metadata) auto-merge with `gh pr merge <num> --auto --squash`. This diff qualifies. |
| PR title format for a docs-only fix that closes a `fix:`-labeled issue? | `inferable` | inference | Squash-merge titles drive release-please. A pure-docs change to a reference file that alters no runtime behavior is `docs(mutation-testing):`, not `fix:`. This means no version bump — appropriate, since no code ships. If the user wants a `fix:` release tag despite the docs-only scope, they can override the PR title before merge. |

## Consistency Gate

- [x] Intent is unambiguous — the seven corrections in issue #522 are enumerated with concrete file/line-level checks.
- [x] Every behavior/goal maps to an acceptance criterion — items 1–7 in the issue map 1:1 onto criteria 1–7; issue's ask "close on merge" maps to criterion 10; repo-level docs-only auto-merge maps to criterion 11.
- [x] Architecture constrains without over-engineering — single file touched, no adapter or code changes, existing shard-aware content preserved.
- [x] Terminology consistent — "Stryker.NET", `dotnet stryker`, `csharp-stryker-net.md`, "shard config" used consistently across all three artifacts.
- [x] No contradictions between artifacts — non-goals in Architecture align with "not touched" scope in Intent and with criteria that only check the C# KB file.
- [x] Every gap/ambiguity finding is logged — six inference-classified decisions and one out-of-scope deferral, each with explicit rationale.
