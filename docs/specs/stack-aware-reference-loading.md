<!-- spec-version: 1 -->
# Spec: Stack-aware reference loading in test-smell-review, cd-test-architecture, and test-modernize

**Format:** dev-team specs v1
**Issue:** <https://github.com/bdfinst/agentic-dev-team/issues/524>

## Intent Description

Three of the test-strategy skills/agents — `agents/test-smell-review.md`,
`skills/cd-test-architecture/SKILL.md`, and `skills/test-modernize/SKILL.md` —
produce output today that is silently stack-agnostic when it should be
stack-specific. They do not detect the project's stack from manifests, so they
never load `knowledge/test-stack-profiles/<stack>.md` or the references it
points at. The .NET HTTP-consumer reference at
`knowledge/references/csharp-http-client-testing.md` — written explicitly so
`test-smell-review` and `cd-test-architecture` can cite it — is therefore
unreachable from those skills' invocation paths today, and the same gap will
exist for every other stack profile (`node.md`, `spring-boot.md`, `go.md`,
`django.md`, `react.md`, `vue.md`, `ssr-htmx.md`) as their referenced files
land.

This change wires stack-detection into those three skills/agents using the
exact pattern `skills/test-design-advisor/SKILL.md:31, 62` already
demonstrates: detect from manifests, look up the matching profile under
`knowledge/test-stack-profiles/`, and cite the profile (and its referenced
files) by path in stack-specific output. Skill/agent prose stays
**language-agnostic** — no language names, no language-specific patterns
appear in skill/agent body text — so each new stack profile becomes reachable
without further skill edits.

## Architecture Specification

**Components touched (three files):**

- `plugins/dev-team/agents/test-smell-review.md` — add stack detection in the agent's invocation steps; cite the matching profile by path in stack-specific findings.
- `plugins/dev-team/skills/cd-test-architecture/SKILL.md` — add a stack-detection step before the assessment is produced; cite the matching profile in the report's *Target architecture* and *Migration path* sections.
- `plugins/dev-team/skills/test-modernize/SKILL.md` — detect once at workflow entry; pass `--stack <id>` through to `/cd-test-architecture` so the modernize flow does not double-scan.

**Pattern source-of-truth:** `plugins/dev-team/skills/test-design-advisor/SKILL.md:31, 62`. Detection rules and fallback behavior are inherited from that skill — *not* duplicated. Each new skill/agent describes detection in one sentence and references the pattern.

**Detection inputs (per `test-design-advisor`):**

- `package.json` → `node` (refine to `react` / `vue` via dependency check)
- `*.csproj` / `*.sln` → `dotnet`
- `pom.xml` / `build.gradle*` → `spring-boot` when Spring is present, otherwise generic JVM (no profile yet — fall through to "name the missing profile")
- `go.mod` → `go`
- `pyproject.toml` / `requirements.txt` → `django` when Django is present, otherwise generic Python
- Frontend SSR (`templates/*.html` + htmx in `package.json`) → `ssr-htmx`

Detection is **best-effort and silent on miss**: if no profile matches, the skill/agent produces stack-agnostic output and **names the missing profile in its report** — same fallback `test-design-advisor` uses (`SKILL.md:62`). Detection never blocks.

**Handoff between `test-modernize` and `cd-test-architecture`:** `test-modernize` adds detection in Step 0 (Approach contract), records the result in `memory/test-modernize/<slug>/phase-0.md`, and forwards `--stack <id>` to `/cd-test-architecture` in Phase 1. `cd-test-architecture` accepts `--stack <id>` as an optional override; when absent (direct invocation), it detects independently. This keeps each skill standalone while avoiding redundant detection in the orchestrated flow.

**Citation policy:** stack-specific findings cite by knowledge path (e.g. `knowledge/test-stack-profiles/dotnet.md`, `knowledge/references/csharp-http-client-testing.md`). No additional `Read` at invocation time — the model already has the path; the user/operator can open it. This matches how `component-test-patterns.md` and `cd-test-architecture.md` already cross-link.

**Out of scope (explicit, do not bundle):**

- No changes to `test-design-advisor` (already correct).
- No changes to knowledge files (`dotnet.md` and friends already cite the references).
- No new shared `detect-stack.sh` helper (rejected in the approach contract — each skill/agent detects independently).
- No new eval fixtures (verification is manual on a .NET fixture, evidence in PR).
- No language-specific prose added to skill/agent bodies.

**Constraints:**

- Skill/agent prose must remain language-agnostic. Manifest names (`package.json`, `*.csproj`, etc.) appear only as the detection input list — no language names, framework names, or language-specific patterns in body text.
- `--stack` is optional everywhere. Skills must work identically when it is absent (detect themselves) and when it is given (trust the override).
- No change to existing argument-hint headers beyond adding `[--stack <id>]` where applicable.
- Frontmatter version in `cd-test-architecture` and `test-modernize` must be bumped per repo convention (the changes alter the skill's argument contract).

**Risk surface:**

- `test-modernize` argument forwarding to `cd-test-architecture` must not break the existing local-files / tracker dispatch — `--stack` is purely additive.
- The `test-modernize` Phase-0 batch already surfaces several ambiguities; adding stack detection there must not add a question the operator has to answer (detection is silent).

## Acceptance Criteria

Each criterion is a deterministic, observable check.

**A1. `test-smell-review` agent has a documented stack-detection step.**

- The agent's Markdown body contains one section (heading or bulleted note) describing manifest-based stack detection in the same shape as `test-design-advisor/SKILL.md:31`.
- The agent's "Detect" or "Knowledge Files" section names `knowledge/test-stack-profiles/<stack>.md` as a load-on-stack-match source.
- Grep verification: `grep -E "test-stack-profiles" plugins/dev-team/agents/test-smell-review.md` returns at least one match.
- Negative grep: `grep -Ei '\b(C#|\.NET|csharp|dotnet|HttpClient|HttpMessageHandler)\b' plugins/dev-team/agents/test-smell-review.md` returns zero matches outside frontmatter/code-fence blocks. (Prose stays language-agnostic.)

**A2. `cd-test-architecture` skill has a documented stack-detection step.**

- The skill's "Parse Arguments" section accepts an optional `--stack <id>` flag with a one-line description and a default of "detect from manifests".
- The skill's Steps section (typically Step 1 or a new Step 0/1.5) describes loading `knowledge/test-stack-profiles/<stack>.md` after detection / when `--stack` is given, with the fallback "name the missing profile" behavior copied verbatim from `test-design-advisor/SKILL.md:62`.
- The skill's *Target architecture* output table is required to cite the loaded profile in the *Test type* / *Double* column when a profile matched.
- Grep verification: `grep -E "test-stack-profiles" plugins/dev-team/skills/cd-test-architecture/SKILL.md` returns at least one match; `grep -E "\\-\\-stack" plugins/dev-team/skills/cd-test-architecture/SKILL.md` returns at least one match.
- Negative grep: same as A1, on `cd-test-architecture/SKILL.md`.

**A3. `test-modernize` skill detects once and forwards `--stack`.**

- The skill's "Approach contract" (Step 0) documents stack detection.
- The Phase-1 invocation line for `/cd-test-architecture` includes `--stack <id>` in its argument list.
- The skill records the detected stack in `memory/test-modernize/<slug>/phase-0.md` alongside the existing recorded inputs.
- Grep verification: `grep -E "\\-\\-stack" plugins/dev-team/skills/test-modernize/SKILL.md` returns at least one match in the Phase-1 invocation block.
- Negative grep: same as A1, on `test-modernize/SKILL.md`.

**A4. Pattern parity with `test-design-advisor`.**

- The detection rules and fallback wording in each of the three updated files are functionally equivalent to `test-design-advisor/SKILL.md:31, 62` (manifest list, stack key, "name the missing profile" fallback).
- Manual side-by-side comparison documented in the PR description.

**A5. Manual verification on a .NET fixture, captured as PR evidence.**

- Run `/cd-test-architecture` against any .NET target (a small `*.csproj` fixture in the repo, an external repo on the operator's machine, or a synthetic one created for the verification) with no `--stack` argument; the produced `reports/cd-test-architecture-<app>.md` cites `knowledge/test-stack-profiles/dotnet.md` in the *Target architecture* section, and (because the profile cross-links to it) `knowledge/references/csharp-http-client-testing.md` appears in the report when outbound HTTP code paths are present.
- Run `/test-smell-review` against a .NET test file that exhibits at least one of the smells catalogued at `csharp-http-client-testing.md:189`; the finding cites `knowledge/references/csharp-http-client-testing.md` by path.
- The PR description embeds both report excerpts as evidence.

**A6. CI/eval pass.**

- `/agent-audit` passes (no structural-compliance regressions in the three edited files).
- `bats` and `shellcheck` suites pass locally (no shell changes, but the pre-push hook runs them).
- `release-please` PR title prefix: `feat:` (new stack-aware behavior). Per repo rule, this PR touches agents and skills — explicit human merge required, `--no-auto-merge` will be passed to `/pr`.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| Each skill/agent detects independently vs. shared helper | `requires-stakeholder-input` | human (approach contract) | Each skill/agent detects independently. Matches `test-design-advisor`; no new shared script. |
| `/test-modernize` → `/cd-test-architecture` stack handoff mechanism | `requires-stakeholder-input` | human (approach contract) | `test-modernize` detects once, passes `--stack <id>`; `cd-test-architecture` also detects when invoked directly. |
| Stack-specific findings cited by path vs. file Read at invocation | `requires-stakeholder-input` | human (approach contract) | Cite by knowledge path in finding prose; no extra Read at invocation time. |
| Acceptance evidence = eval fixture vs. manual run | `requires-stakeholder-input` | human (approach contract) | Manual verification against a .NET fixture, evidence in PR. |
| Where in `test-smell-review` the detection note lives (Detect section vs. Knowledge Files section) | `inferable` | inference | Add to "Knowledge Files" section since stack profiles **are** knowledge files; mention in "Detect" as a one-line cross-reference. Matches `test-design-advisor` layout. |
| Whether `cd-test-architecture` adds the detection as new Step 0 or extends Step 1 | `inferable` | inference | Extend "Parse Arguments" (for `--stack`) and add a "Step 0 — Detect stack" subsection above existing Step 1, so the inventory step in Step 1 can rely on the resolved stack. Minimum disruption to existing step numbering — no later step needs renumbering. |
| Whether `--stack` needs to flow through to `/issues-from-assessment` from `/test-modernize` | `inferable` | inference | No. `/issues-from-assessment` reads the assessment report; the stack identifier is already cited in the report by `/cd-test-architecture`. Adding a redundant flag would expand the change. |
| Frontmatter `version:` bump | `inferable` | inference | The three files don't carry a `version:` field today; only argument-hint changes. No bump needed unless the file already has one. release-please picks up `feat:` from the PR title. |
| Skip behavior when detection produces no profile match | `inferable` | inference | Exactly as `test-design-advisor` does: produce stack-agnostic output and **name the missing profile** in the report. No new logic; reuse the wording. |
| Adding `--stack <id>` to skill `argument-hint` strings | `inferable` | inference | Yes for `cd-test-architecture` and `test-modernize` (operator-facing). `test-smell-review` is not directly user-invocable — no hint to update. |

No `LOW_VALUE` items.

## Consistency Gate

- [x] Intent is unambiguous — *Wire the three named files to detect stack from manifests, look up a profile in `knowledge/test-stack-profiles/<stack>.md`, cite by path, fall back silently when no profile matches. Skill/agent prose stays language-agnostic.*
- [x] Every behavior/goal maps to an acceptance criterion — A1 (test-smell-review), A2 (cd-test-architecture), A3 (test-modernize), A4 (pattern parity), A5 (manual evidence), A6 (CI).
- [x] Architecture constrains without over-engineering — three files edited; no shared helper, no new knowledge files, no eval fixtures, no language-specific prose.
- [x] Terminology consistent across artifacts — *stack profile*, *stack identifier*, *language-agnostic*, *cite by knowledge path* used identically.
- [x] No contradictions between artifacts — the four locked decisions appear identically in Intent, Architecture, Acceptance, and Ambiguity Log.
- [x] Every gap/ambiguity finding is logged — ten findings, four resolved by human, six inferable with explicit rationale, zero undocumented assumptions.

**Verdict: PASS.** Ready for `/plan`.
