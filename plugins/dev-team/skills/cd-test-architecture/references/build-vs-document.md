# Build-vs-document decision and test-double setup guide

Reference for `SKILL.md` Step 4 and Step 6. The two sections below move verbatim out of the skill body; the procedure is unchanged. Step 4b is the skill's one interactive branch point. The Companion section is written during Step 6.

### 4b. Build-vs-document decision (adapter test doubles)

When Step 4 identifies one or more components needing an adapter test double (today: a testcontainers-based real-DB test, or a downstream-service adapter test; a component test using a per-test isolated instance is not a 4b option), ask the operator once per run, batched across every such component regardless of adapter kind — this is the shared prompt every adapter-kind slice appends to, not a new prompt each run; the Downstream-service branch below, including its record-and-replay-library sub-question, is one such append, already shipped, not future work. The one prompt lists every such component and asks the operator, for each one, to choose exactly one of three options — there is no separate follow-up sub-question (a `Build (Fake)` row's construction-method sub-question is carried in this same prompt and reply — see the Downstream-service branch below):

1. **Build (testcontainers)** — propose a downstream Story for a real-dependency test using testcontainers (exact Story shape per the branch subsection below).
2. **Build (Fake)** — propose a downstream Story for a hand-rolled Fake double (exact Story shape per the branch subsection below).
3. **Document-only** (default) — the recommendation lands in the report as today, with no further action.

The operator answers with one of these three choices for each listed component in a single reply — one prompt is surfaced per run, carrying a per-component three-way answer, not one verdict applied to every component in the batch.

Non-interactive runs (per `human-oversight-protocol`'s `--yes` / `DEV_TEAM_AUTO_APPROVE=1` / no-TTY convention) skip the prompt entirely — no prompt is surfaced, and every such component's recommendation lands in the report only, document-only, exactly as today.

An ambiguous or absent answer for any component in the batched three-way question — for example "maybe", "I'm not sure", a bare "yes" or "no", an unqualified "build" that does not name which of the two Build options (none of these map to one of the three labeled options), or silence/empty input — defaults to Document-only for that component, same as any other ambiguous answer: never guessed, never blocked on.

Repos with no such gap see no behavior change: no prompt is asked, and the report is unchanged.

#### Database-specific branch

For the database-IS-the-SUT band, the three-way answer directly determines the outcome per component:

- **Build (testcontainers)** — propose a Story titled `[<component>] Add testcontainers-based real-DB adapter integration test`. Its description names Database Sandbox isolation and both teardown options — Transaction Rollback and Table Truncation — cites `database-test-patterns.md`, and states the test verifies the adapter's SQL and mapping against the real engine and runs out-of-band on a schedule, never pre-merge.
- **Build (Fake)** — propose a Story titled `[<component>] Add hand-rolled Fake database double`. Its description names the Fake as an in-memory repository implementing the same interface, per `test-doubles.md`'s Fake taxonomy, cites both `database-test-patterns.md` and `test-doubles.md`, and always carries this caveat verbatim: "Caveat: this hand-rolled Fake cannot verify actual SQL, mapping, or schema correctness the way a real-engine test can — a deliberate coverage trade-off, not a silent downgrade."
- **Document-only** — the recommendation lands in the report only, as today; no further action.

#### Downstream-service branch

Applies to API Consumer, Event Consumer, and Event Producer components (`component-test-patterns.md`) that Step 4 flagged for the same adapter-test-double decision as the database branch above — added to the *same* batched per-run prompt, not a second prompt: the shared prompt above already states later adapter-kind slices append here, and this is that append.

Every row offers all three options identically, with no ownership-based distinction: `Build (testcontainers)`, `Build (Fake)`, `Document-only`.

**All off-gate validation of a downstream-service test double runs out-of-band, on a schedule — never pre-merge/in-band — regardless of whether the dependency is team-controlled or third-party.** This applies uniformly to the testcontainers-based adapter-integration test, the hand-rolled Fake's companion provider-contract verification, and the library-backed double's re-record/diff companion action alike, per the placement rule in `component-test-patterns.md`'s Pipeline lines and `cd-test-architecture.md`'s The Pre-Merge Gate Rule.

An ambiguous or absent answer for a downstream-service row defaults to `Document-only`, the same ambiguous-answer rule as any other ambiguous answer above — not a new rule.

**When the top-level answer for a row is `Build (Fake)`, a second, narrower sub-question resolves which construction method to use — asked in the same single batched prompt and reply as the top-level three-way choice above, never a follow-up round-trip.** The sub-question applies only to rows where the operator chose (or defaulted to) `Build (Fake)`; a `Build (testcontainers)` or `Document-only` row carries no such sub-question, and any install/decline preference volunteered for either of those rows is ignored, not an error. The answer grammar is explicit and three-valued, not binary: (a) accept the recommended virtual-service library (the existing-tool-detected or catalog default, per `virtual-service-libraries.md`'s Resolution order), (b) name a specific different library, or (c) decline (hand-rolled Fake, the backup).

**An ambiguous or absent sub-answer defaults to (a), installing the recommended library — the preferred solution — not (c) decline.** This is a distinct, narrower default rule from the top-level three-way choice's own ambiguous-answer default stated above, which remains `Document-only`, unchanged: the library is preferred and hand-rolled is backup, so the safer default when this narrower sub-question is unspecified is the preferred option, not the fallback. An operator's explicit-accept answer (e.g. "Build (Fake), accept") installs the recommended library identically to this ambiguous/absent-answer case.

For an Event Consumer/Producer row whose broker protocol has no protocol-appropriate virtual-service library (per `virtual-service-libraries.md`'s broker-tooling note), this sub-question is not presented at all — the row states plainly that no such library exists for its protocol, and defaults to the hand-rolled Fake Story below, with no tool name substituted.

Each selected option proposes a Story, following the database branch's shape:

- **Build (testcontainers)** — propose a Story titled `[<component>] Add testcontainers-based adapter integration test`. Its description exercises the real outbound client against a testcontainers-hosted, protocol-compatible instance, states the test runs out-of-band on a schedule (never pre-merge/in-band), and cites the relevant `component-test-patterns.md` pattern (API Consumer / Event Consumer / Event Producer — name whichever applies). (Maintainer note, not emitted Story content: #1435 deliberately scoped the record-and-replay library-preference sub-question below to the `Build (Fake)` row only — this bullet carries no tool-selection language, enforced by `test_sub_question_only_applies_to_build_fake_row` in `tests/skills/test_cd_test_architecture_virtual_service_libraries.py`.)
- **Build (Fake)** — propose a Story titled `[<component>] Add hand-rolled Fake downstream-service double`. Its description names a hand-rolled Fake behind a team-owned thin adapter, per `test-doubles.md`'s Fake taxonomy, and cites `component-test-patterns.md`. When the sub-answer above resolves to (c) decline, the Story always carries this caveat verbatim: "Caveat: this hand-rolled Fake cannot verify that the adapter actually satisfies the real service's wire contract — pair it with scheduled provider-contract verification against the provider's real environment, per the API Consumer / Event Consumer / Event Producer patterns." The Story always — no ownership-based exemption — additionally proposes scheduled, out-of-band provider-contract verification against the dependency's real environment as a companion action, not a fourth option. When the sub-answer above resolves to installing a library instead (default, named override, or explicit accept), the Story title instead becomes `[<component>] Add <tool-name>-backed downstream-service double` (e.g. `[<component>] Add Nock-backed downstream-service double`), naming the concrete tool chosen, and its description states the library-backed double runs in-band (pre-merge, per `cd-test-architecture.md`'s The Pre-Merge Gate Rule); this library-backed outcome carries its own one-line caveat in place of the hand-rolled-Fake wire-contract caveat above — no wire-contract caveat is needed for a library-backed double, because the library's own off-gate re-record/diff validation (below) is what keeps it honest, not a hand-rolled assumption about the wire contract; the same scheduled provider-contract-verification companion action described above is unchanged in count — still one, not a second, additional off-gate test artifact — only its *mechanism* changes: for a library-backed double, that action is the library's own re-record/diff capability against the real dependency (when the chosen tool has one), in place of a hand-rolled contract test. When the chosen library has no re-record/diff capability, the companion action reverts to the hand-rolled provider-contract verification described earlier in this bullet — still one artifact, not a second one.
- **Document-only** — the recommendation lands in the report only, as today; no further action.

### Companion: test-double setup guide

Whenever Step 4's Target architecture table recommends a testcontainers-based
adapter integration test (`Build (testcontainers)`), a virtual-service-library-backed double, or a hand-rolled fallback for
any component (a per-test isolated instance does not trigger it), write a companion **test-double setup guide** — independent of
that component's Step 4b Build/Document-only outcome: this applies even when
the operator chose Document-only for that component, or the run was
non-interactive, and the setup guide still includes that component's section
exactly as it would if the operator had chosen to build it.

**Path.** Write the guide to
`.dev-team-reports/cd-test-architecture-<app>-test-double-setup.md` — the
main report's own filename (`cd-test-architecture-<app>.md`) with its `.md`
extension replaced by `-test-double-setup.md`, same directory and naming
convention as the main report, never a legacy path outside
`.dev-team-reports/`. In the single-component chat-only case (the
main report goes to chat, not a file), the setup guide's content is appended
to that same chat output instead of written as a second file. When no
component in the run falls into this adapter-double decision space,
write no setup-guide file or chat section at all — never an empty one.

**Header and Provenance.** For the header block and closing Provenance
section, follow `knowledge/report-template.md`; the per-component sections
below are this guide's own body. `**Scope**` reads the components covered by
this guide — the components with a per-component section below, not the
full application inventory from Step 1.

**Per-component sections.** One section per component — even when two
components resolve to the same tool, each still gets its own section with
its own component-specific example prompt. A non-adapter-double component (no
adapter-double recommendation at all) gets no section. Each section has:

1. **Tool name + one-line purpose.**
2. **Doc link** to the tool's official documentation — omitted only for the
   hand-rolled-fallback case (there is nothing to link to for hand-rolled
   code); the other three elements still apply to that case.
3. **Configuration steps** that cite — never restate — the same
   `test-stack-profiles/<stack>.md` entry (and, for the virtual-service-
   library case, the `virtual-service-libraries.md` entry) Step 4 already
   resolved for that component's `Double` column. When Step 0 resolved no
   stack profile for the component, state that plainly (e.g. "No matching
   stack profile for this component") rather than citing a profile that was
   never resolved.
4. **One concrete, ready-to-run example prompt** naming the actual component
   and tool — never a generic template placeholder.
5. The closing command `/apply-test-doubles <path>`, where `<path>` is
   always the **main assessment report's own resolved path**
   (`.dev-team-reports/cd-test-architecture-<app>.md`), never the setup
   guide's own path — per `../../apply-test-doubles/SKILL.md`'s own Parse
   Arguments section, not restated here. In the
   single-component chat-only case, there is no saved main-report file to
   substitute for `<path>` — the assessment output is in this chat session,
   not a saved file — so the closing command is emitted with no path
   argument (plain `/apply-test-doubles`), never falling back to the setup
   guide's own path.

**Classification** — cited from Step 4b's branches above, not invented here:

- **Testcontainers** (Database-specific or Downstream-service branch, `Build
  (testcontainers)`) — name the testcontainers tool.
- **Virtual-service library** (Downstream-service branch, `Build (Fake)`
  resolving to a library) — name whichever tool Step 4b's Downstream-service
  branch's construction-method sub-question resolved for this component
  (see that branch above — not restated here). Caveat: this case's
  configuration steps must also cite `virtual-service-libraries.md`'s
  "Recorded artifacts contain real traffic — scrub before commit" section
  (in addition to the per-tool catalog entry) and name that tool's
  credential-filtering hook as a step ordered before the first recording,
  never after.
- **Hand-rolled fallback** (`Build (Fake)` resolving to hand-rolled, or Step
  4b's Downstream-service branch's no-matching-library fallback applying to
  this component's adapter kind — see that branch above, not restated here)
  — no doc link; the other three elements (name+purpose, configuration
  steps, and the example prompt) still describe the specific
  fake/contract-test to write for that component.

**Downstream-service components with no posed sub-question.** For a
Downstream-service component whose construction-method sub-question was
never posed or answered (the operator chose Document-only, the run was
non-interactive, or the top-level answer was ambiguous), classify it using
the same tool-resolution rule Step 4b's sub-question applies when it does
fire — see the Downstream-service branch above for what determines the
tool, not restated here — applied to rows that never got a sub-question in
the first place, because this guide's trigger is independent of the
Build/Document-only outcome, never a guess and never omitted. It falls back
to the Hand-rolled fallback classification above only when Step 4b's own
no-matching-library condition applies for this component's adapter kind —
again, see that branch, not restated here. This three-case list is
illustrative of "no sub-question ever reached this row"; it excludes the
separate case where a `Build (Fake)` row's sub-question WAS posed but got an
ambiguous or absent answer, which Step 4b's own stated default for that case
already resolves (see that branch above), not this fallback. A
volunteered-but-ignored install/decline preference on a Document-only row is
likewise not honored by this fallback either — per Step 4b's own "ignored,
not an error" framing, it defers to Step 4b's own resolution rule above (not
restated here), never the operator's stated-but-disregarded preference.
