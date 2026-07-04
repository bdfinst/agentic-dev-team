<!-- spec-version: dev-team-8.3.4 -->
# Spec: Honest Mutation Score & Survivor Triage (issue #521)

**Format:** dev-team `/specs` v8.3.4
**Issue:** [#521 — feat: improve Stryker.NET score accuracy and survivor triage in mutation-testing skill](https://github.com/bdfinst/agentic-dev-team/issues/521)

## Intent Description

The `mutation-testing` skill reports a single headline mutation score that
counts timeouts as kills, which — on real Stryker.NET runs — has inflated
reported scores from ~23 % honest to 61 % claimed (999 of 1305 "kills" were
timeouts). The score is a lie under load. The skill also treats every
surviving mutant the same, even though the fixes are fundamentally different:
`String`/`ObjectInitializer`/`Equality` mutants need a specific-value
assertion, `Statement`/`Block` mutants need a test that reaches an
unexercised path (a stronger assertion cannot kill them), `Guard` mutants
need a unit test that invokes the guarded method directly with invalid input.
And a `NoCoverage` mutant — code no test reaches at all — is quietly worse
than a survivor, but the skill never names it.

This change makes the honest score the operator's primary signal, warns when
the timeout share is high enough to have corrupted the headline score, and
teaches the triage step to distinguish the three mutation-type families and
prioritize `NoCoverage` above survivors. It also adds probe-file selection
guidance so the first Stryker run against a repo produces a signal-bearing
result instead of a mass-CompileError smoke plume.

The change is skill-content only: `SKILL.md`, `references/languages/csharp-stryker-net.md`, and the machine-readable JSON schema documented in `SKILL.md`. No adapter script or hook changes ship here — adapters emit whatever fields the mutation tool reports; the schema is additive so existing readers keep working.

## Architecture Specification

**Affected components**

- `plugins/dev-team/skills/mutation-testing/SKILL.md` — output format, JSON schema doc, Step 3 (parse), Step 4 (triage), Step 2 (probe selection guidance, language-agnostic).
- `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` — Stryker.NET-specific probe-file avoidance list (gRPC/Protobuf, Caching under `Standard`).
- **No adapter script changes.** Per-tool adapters compute what their native reports contain; Stryker.NET's `mutation-report.json` already carries `Timeout`, `NoCoverage`, `CompileError`, `Ignored` — the change is documenting the derivation, not adding a computation step.

**Contracts**

- **JSON schema stays at `schema_version: 1`.** Additive-only: new optional fields `honest_score`, `claimed_score`, `timeout_pct`, `no_coverage`, `timeout_warning`. Readers built against the current schema keep working; readers that consume the new fields must tolerate them being absent (advisory-only tools like go-mutesting will not emit them).
- **Which adapters emit the new fields:** any adapter whose native tool distinguishes Timeout / NoCoverage — Stryker.NET, Stryker (JavaScript), pitest, mutmut. Adapters whose tools do not distinguish (go-mutesting) omit the fields entirely rather than emit `0` — silent zeros misreport reality.
- **Formulas** (adopted from the sibling `mutation-kill` agent, PR #528 / commit `60534fd`, to keep both surfaces in sync):
  - `honest_score   = Killed / (Killed + Survived + NoCoverage)`
  - `claimed_score  = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)`
  - `timeout_pct    = Timeout / (Killed + Survived + Timeout)`
  - `timeout_warning = timeout_pct > 0.05`
- **Human-readable output** shows honest score first, claimed score second, and — when `timeout_warning` is true — a callout naming `additional-timeout` as the tuning knob before the score is used as a gate.
- **Triage ordering:** `NoCoverage` items appear before `Survived` in the recommended work order. Rationale is stated in-line in the triage table: a NoCoverage path was never reached; a survivor at least ran, so its assertion can be tightened without changing coverage.
- **Mutation-type-aware guidance** is a new sub-section under Step 4. Three families:
  - `String` / `ObjectInitializer` / `Equality`: fix by adding a specific-value assertion on the affected field. Example asserts a specific string / equality, not a status code.
  - `Statement` / `Block` removal: fix by adding a test that reaches the missing code path. Named counter-example: "do not ask an LLM to kill a Statement mutation with a stronger assertion."
  - `Guard` (null-check / range-check / required-field removal) on internal service methods: fix by calling the guarded method directly with invalid input and asserting the exception. Guard survivors are identified by looking for `Statement` survivors in service/builder classes.
- **Probe file selection guidance** lives in two places, per stakeholder direction:
  - Language-agnostic rule in `SKILL.md` Step 2: pick a probe file with **≥ 50 mutants** and the **highest existing mutation score** in the target; avoid generated code, DTOs, and files with near-0 % coverage.
  - C#-specific avoidance list in `csharp-stryker-net.md`: gRPC/Protobuf service implementations (mass CompileErrors from `ObjectInitializer` mutations on Protobuf types), Caching / key-building classes under `mutation-level: Standard` (LinqMutation / StringMutation generate methods that do not exist — `StringBuilder.Prepend`, `IDictionary.Sum` — producing 1000+ CompileErrors).

**Non-goals**

- Not changing any adapter script's parsing logic (adapters already surface these counts; the change is documentation-only).
- Not touching `mutation-kill.md` (the sibling agent's honest-score wording landed on Issue-528 and will merge separately).
- Not adding new eval fixtures for adapter output (schema is additive; existing fixtures remain valid).
- Not adding a hook or hard gate that fails a run when `timeout_pct > 5 %` — the warning is advisory. Making it a gate is a policy decision for a follow-up.

## Acceptance Criteria

Each criterion is either a diff-visible artifact (verifiable by `grep`, structural inspection, or CI check) or a behavior a following operator can observe.

1. **`SKILL.md` output-format block names both scores.** The rendered `## Mutation Testing Results` example includes an `Honest score` line and a `Claimed score` line (in that order), with the honest score above the claimed score. Grep proof: `grep -c "Honest score" plugins/dev-team/skills/mutation-testing/SKILL.md` returns `≥ 1`.
2. **`SKILL.md` JSON schema example includes the additive fields.** The `schema_version: 1` block in `## Machine-readable output` contains keys `honest_score`, `claimed_score`, `timeout_pct`, `no_coverage`, and `timeout_warning`. Grep proof: `grep -c '"honest_score"' plugins/dev-team/skills/mutation-testing/SKILL.md` returns `≥ 1` for each field.
3. **Formulas are documented next to the schema.** The formulas — `honest_score = Killed / (Killed + Survived + NoCoverage)` and `claimed_score = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)` — appear once in `SKILL.md`, in the same section as the schema example, in a bash/code fence so they are unambiguous.
4. **`schema_version` stays at `1`.** No place in `SKILL.md` refers to `schema_version: 2` or a schema bump.
5. **Timeout warning is defined and observable.** `SKILL.md` states `timeout_warning = timeout_pct > 0.05`, that human output surfaces the warning when true, and that the recommended remediation is raising `additional-timeout` before treating the score as a gate.
6. **Which adapters emit the fields is documented.** `SKILL.md` names the emitting adapters (Stryker, Stryker.NET, pitest, mutmut) and states advisory-only adapters (go-mutesting) omit the fields — with a short line explaining that omission is intentional so readers do not misinterpret zeros.
7. **`NoCoverage` is a first-class triage category.** The Step 4 triage table lists a `NoCoverage` row with `Meaning = "No test exercises this code path at all"` and `Action = "Add a test that reaches the path before worrying about killing the mutant"`. The recommended work order in Step 4 places `NoCoverage` **before** `Survived`.
8. **Mutation-type-aware triage section exists.** A new sub-section under Step 4 (heading text contains `Mutation-type-aware`) covers three families with the guidance summarized above: String/ObjectInit/Equality → specific assertion, Statement/Block → coverage, Guard → unit test that invokes the method directly. The Statement/Block bullet explicitly says a stronger assertion cannot kill it.
9. **Probe file selection guidance — language-agnostic — lives in `SKILL.md` Step 2.** Step 2 documents: pick a probe with ≥ 50 mutants and the highest existing mutation score in the target; avoid generated code, DTOs, and files with near-0 % coverage. Grep proof: `grep -c "50" plugins/dev-team/skills/mutation-testing/SKILL.md` returns a line matching probe guidance.
10. **Probe file selection guidance — C# specifics — lives in `csharp-stryker-net.md`.** The Stryker.NET reference names two avoidance categories with their failure modes: (a) gRPC/Protobuf service implementations (mass CompileErrors from `ObjectInitializer` mutations on Protobuf types) and (b) Caching / key-building classes under `mutation-level: Standard` (LinqMutation / StringMutation generate non-existent methods — `StringBuilder.Prepend`, `IDictionary.Sum` — producing 1000+ CompileErrors).
11. **No adapter script (`.sh`, `.py`) is modified by this PR.** The diff touches only `SKILL.md`, `csharp-stryker-net.md`, and any test file added to validate the doc changes. Grep proof: PR diff summary shows exactly those two markdown files (plus tests if any).
12. **PR title uses conventional-commit `feat:` prefix.** Release-please reads the PR title on squash-merge; the issue is titled `feat:` so the PR is `feat(mutation-testing): honest score, timeout warning, NoCoverage-first triage, mutation-type guidance (#521)` or an equivalent `feat(mutation-testing): …` form.
13. **Auto-merge is armed at PR open time.** After `gh pr create`, `gh pr merge <num> --auto --squash` is invoked. (Note: this overrides the default policy — see Ambiguity Log entry AL-3.)
14. **`/agent-audit` passes** against the modified `SKILL.md` and language reference (validates frontmatter, cross-references, and structural conformance).

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| AL-1: Which per-tool adapters emit the new fields? | `requires-stakeholder-input` | human | "All adapters that can compute them" — Stryker.NET, Stryker.JS, pitest, mutmut emit; go-mutesting omits (does not distinguish Timeout/NoCoverage). Rejected the "all adapters, emit 0 when unknown" option because silent zeros misrepresent reality. |
| AL-2: Which formulas govern — the issue's `(Total − Ignored − CompileError)` denominator or the sibling `mutation-kill` agent's `(Killed + Survived + NoCoverage)` denominator? | `requires-stakeholder-input` | human | "Adopt the Issue-528 formulas." The two surfaces stay in sync; the mutation-kill agent already ships this shape on the Issue-528 branch. `honest_score = Killed / (Killed + Survived + NoCoverage)`; `claimed_score = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)`. Documented divergence from Stryker's own line noted in the schema section. |
| AL-3: Auto-merge or explicit human merge? | `requires-stakeholder-input` | human | "Arm auto-merge" — user explicitly overrode the default (skills are shipping components; the CLAUDE.md docs-only carve-out would normally exclude them). This is a per-PR override, not a policy change; recorded here so the plan does not silently walk it back. |
| Probe guidance scope: C# only, language-agnostic + C#, or all five references? | `requires-stakeholder-input` | human | "Language-agnostic + C# specifics." General rule (50+ mutants, highest score, avoid generated/DTO/near-0 %) in `SKILL.md` Step 2; Stryker.NET-specific avoidance (Protobuf, Caching+Standard) in `csharp-stryker-net.md`. |
| Should `timeout_warning = true` be a hard gate that fails the run? | `inferable` | inference | No. The issue describes a warning, not a gate. Making it a gate would break existing runs the moment they land in a repo with a low `additional-timeout` — a policy decision that belongs in a follow-up. Advisory-only per issue text. |
| Do adapter scripts need a code change to emit the new fields? | `inferable` | inference | No. Stryker.NET's `mutation-report.json` already carries `Timeout`, `NoCoverage`, `CompileError`, `Ignored` per its schema; adapter shells already surface the counts. The change is documentation of derivation. If a probe run reveals an adapter that does not surface a count, that becomes a follow-up issue rather than expanding this spec's scope. |
| Should `mutation-kill.md` be updated in this PR to reference the new field names? | `inferable` | inference | No. The mutation-kill agent already uses the same formulas via PR #528 (Issue-528 branch). Cross-referencing across in-flight branches would create merge conflicts. Reconcile in a follow-up once both land on `main`. |

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret it the same way (the intent names the specific failure mode — 999 of 1305 "kills" being timeouts — and the three mutation-type families explicitly).
- [x] Every behavior/goal in the intent maps to at least one acceptance criterion (honest score → AC-1/AC-3; timeout warning → AC-5; NoCoverage-first → AC-7; type-aware triage → AC-8; probe guidance → AC-9/AC-10; schema stability → AC-2/AC-4/AC-6; no code drift → AC-11).
- [x] Architecture constrains implementation to what the intent requires, without over-engineering (schema stays at v1; no adapter changes; probe guidance split between the two files as the stakeholder asked).
- [x] Terminology consistent across artifacts (`honest_score`, `claimed_score`, `timeout_pct`, `timeout_warning`, `no_coverage`, `NoCoverage`, `additional-timeout` are used identically in Intent, Architecture, and Acceptance Criteria).
- [x] No artifact contradicts another (formulas appear once, only in Architecture and mirrored in AC-3 as a grep target).
- [x] Every gap/ambiguity finding is logged (Ambiguity Log has entries for both stakeholder-input questions the user answered, plus three inferred items with explicit rationale).

**Verdict: PASS.**
