<!-- spec-version: 8.4.0 -->
# Spec: mutation-testing — recommend local install with language-specific install commands

Tracking issue: [#549](https://github.com/bdfinst/agentic-dev-team/issues/549).

## Intent Description

The `mutation-testing` skill currently defers *all* install guidance to each `references/languages/<lang>.md` and does not steer users toward a **local**, project-scoped install. Global installs depend on the user's `PATH` and produce silent "command not found" failures — this was observed for Stryker.NET on macOS Homebrew and diagnosed in `references/languages/csharp-stryker-net.md`, which has already been updated to the tool-manifest pattern with a `dotnet stryker --version` visibility probe.

This change lifts that pattern to the skill level so it applies to *every* language, not just C#. The language-agnostic `SKILL.md` will state up front that a local install is preferred, and each language reference will lead with its language's local-install command plus a one-liner probe that confirms the tool resolves. Go-mutesting is the honest exception (`go install` writes to `$GOPATH/bin`) and will explicitly call out the `PATH` requirement rather than pretend otherwise.

The result is one consistent install narrative across all five language paths, closing the class of silent-failure traps that motivated the original bug report.

## Architecture Specification

**Scope of change.** Documentation only. No code, no tooling, no detection-logic changes.

**Files modified:**

| File | Change |
|------|--------|
| `plugins/dev-team/skills/mutation-testing/SKILL.md` | Add a "Prefer a local install" paragraph to *Step 1: Detect or set up tooling*, before the language-file handoff. Wording per issue #549. |
| `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` | Already updated (model reference). Verify visibility probe (`dotnet stryker --version`) is present. |
| `plugins/dev-team/skills/mutation-testing/references/languages/javascript-stryker.md` | Confirm `npm install --save-dev …` is presented as local (it is; verify wording). Add `npx stryker --version` visibility probe. |
| `plugins/dev-team/skills/mutation-testing/references/languages/python-mutmut.md` | Lead with venv-scoped `pip install mutmut` or `pyproject.toml [project.optional-dependencies] dev`; call out venv scope explicitly. Add `mutmut --version` visibility probe. |
| `plugins/dev-team/skills/mutation-testing/references/languages/java-pitest.md` | Confirm plugin declaration in `pom.xml` / Gradle is presented as project-scoped by design. Add Maven visibility probe: `./mvnw org.pitest:pitest-maven:help -Ddetail=true -Dgoal=mutationCoverage \| head -1`. |
| `plugins/dev-team/skills/mutation-testing/references/languages/go-go-mutesting.md` | Add explicit note that `go install …@latest` writes to `$GOPATH/bin` and requires that directory on `PATH`. Add `command -v go-mutesting \|\| echo "…"` visibility probe. |

**Files NOT modified (non-goals per issue #549):**

- `references/tool-detection.md` — detection logic unchanged.
- No new install-helper script, no `install.sh`, no hooks.
- No knowledge index entry additions — this is edit-in-place within existing files.

**Downstream constraints:**

- Rebuild the knowledge index after edits (`bash plugins/dev-team/hooks/lib/build-knowledge-index.sh`) per the project's `knowledge_index_current.bats` gate.
- Squash-merge PR title must be `docs(mutation-testing): …` (conventional) so release-please picks it up. Docs-only diff → auto-merge is armed at PR-open time (`gh pr merge <num> --auto --squash`).

**Terminology.** "Local install" = a project-scoped install whose invocation resolves from the project directory without a user-configured `PATH` (dotnet tool manifest, `--save-dev` in `node_modules/.bin`, venv-scoped `pip`, Maven/Gradle plugin declaration). "Global install" = anything that requires `$GOPATH/bin`, `~/.dotnet/tools`, or `/usr/local/bin` to be on the user's `PATH`. The C# reference is the canonical model.

## Acceptance Criteria

Every criterion is observable by reading the changed files or running the referenced probe.

1. `plugins/dev-team/skills/mutation-testing/SKILL.md` § *Step 1: Detect or set up tooling* contains a paragraph (before the language-file handoff) recommending a local install over a global one, citing the Stryker.NET case and pointing at each language file for the concrete local-install command. Wording matches the block quoted in issue #549 § 1.
2. `references/languages/csharp-stryker-net.md` § *Install / detect* leads with `dotnet new tool-manifest && dotnet tool install dotnet-stryker` and shows the `dotnet stryker --version` visibility probe. **(Baseline; already satisfied — verified, not re-authored.)**
3. `references/languages/javascript-stryker.md` § *Install / detect* leads with `npm install --save-dev @stryker-mutator/core @stryker-mutator/<runner>-runner`, explicitly labels this as the local (project-scoped) install path, and shows the `npx stryker --version` visibility probe.
4. `references/languages/python-mutmut.md` § *Install / detect* leads with venv-scoped `pip install mutmut` **or** `pyproject.toml [project.optional-dependencies] dev` entry, explicitly calls out that the install is scoped to the active virtual environment, and shows the `mutmut --version` visibility probe.
5. `references/languages/java-pitest.md` § *Install / detect* leads with the Maven `<plugin>` declaration (or Gradle `info.solidsoft.pitest` plugin), explicitly notes it is project-scoped by design, and shows the Maven visibility probe: `./mvnw org.pitest:pitest-maven:help -Ddetail=true -Dgoal=mutationCoverage | head -1`.
6. `references/languages/go-go-mutesting.md` § *Install / detect* explicitly states that `go install github.com/zimmski/go-mutesting/cmd/go-mutesting@latest` writes to `$GOPATH/bin` and that this directory must be on `PATH`, and shows the visibility probe `command -v go-mutesting || echo "go-mutesting not on PATH — check $GOPATH/bin"`.
7. The knowledge index is rebuilt post-edit; `plugins/dev-team/hooks/lib/build-knowledge-index.sh` produces no diff on a follow-up run (CI's `knowledge_index_current.bats` passes).
8. `bats tests/skills/mutation-testing/` — the skill's existing structural/reference tests still pass. No test authored for wording (docs-only, tests would encode prose).
9. The PR title uses a conventional `docs(mutation-testing): …` prefix; the diff touches only the six markdown files above (plus, if needed, the regenerated knowledge index).

**Explicit non-criteria** (from issue #549 § Non-goals): detection logic in `references/tool-detection.md` is unchanged; no install helper script is added.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| Exact wording of the SKILL.md "prefer local install" paragraph | `inferable` | inference | Issue #549 § 1 quotes the exact paragraph verbatim. Use it as written. |
| Java visibility probe form (Maven vs Gradle) | `inferable` | inference | Issue #549 § 3 shows the Maven form (`./mvnw org.pitest:pitest-maven:help …`); the existing `java-pitest.md` documents both Maven and Gradle in the run section but only Maven has a natural help-goal one-liner. Document the Maven probe; note Gradle users can run `./gradlew tasks --group=pitest` as an equivalent — non-blocking addition. |
| Whether Java plugin declaration counts as "local install" for the purposes of the intro paragraph | `inferable` | inference | Yes. A plugin declared in `pom.xml` or `build.gradle` is by definition project-scoped and resolves via the build tool's own dependency resolution — no user-configured `PATH` involved. Frame it that way in the file. |
| Whether Python `pyproject.toml [project.optional-dependencies] dev` alone (without a running venv) is enough | `inferable` | inference | Both wording variants (`pip install` in a venv, or `pyproject.toml` entry) satisfy "local"; venv is the runtime scope, `pyproject.toml` is the declaration. Present both and require the caller select one. |
| Whether the Stryker.NET reference needs a re-audit vs. accept-as-is | `inferable` | inference | Issue #549 says it is the model and "already updated". Verify the two acceptance-criteria items resolve (they do, per the file read), do not rewrite. |
| Should any test file assert on the new wording | `inferable` | inference | No. This is a docs-only change; asserting on prose would encode brittle string matches. The knowledge-index rebuild gate and existing bats tests are sufficient signal. |
| Whether to add a "verify visibility" section to `SKILL.md` itself or leave it in the language files | `inferable` | inference | Issue #549 § 3 places the probe in the language files (one per language). Follow the issue — this keeps `SKILL.md` short and defers detail to the language references, matching the file's existing style. |

No `requires-stakeholder-input` items — issue #549 is exceptionally well-specified.

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion (5 doc changes + rebuild + PR shape → criteria 1–9)
- [x] Architecture constrains without over-engineering (docs only; explicit non-goals list)
- [x] Terminology consistent across artifacts ("local install", "visibility probe", "language reference")
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — all seven items classified `inferable` with rationale; no undocumented assumptions

**Verdict: PASS.** Ready for `/plan`.
