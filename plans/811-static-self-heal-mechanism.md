# Plan: Wire per-step static-analysis self-healing into /build's review checkpoint (#811)

**Created**: 2026-07-04
**Branch**: epic/823/811-static-analysis-mechanism
**Status**: implemented
**Gherkin persistence**: plan-file-only

## Goal

Land the shared static-analysis self-heal **mechanism** that `/build`'s two
existing inline review checkpoints run before their semantic review sequence,
plus the two skeletons the four language issues (#807 Python, #808 JS/TS,
#809 C#, #810 Java) plug into: the "Build-time lanes" registry in
`static-analysis-integration/references/tool-configs.md` and the per-language
setup guide `static-analysis-integration/references/language-setup.md`. The
mechanism lands with **zero registered lanes** and is a structural no-op —
`/build` behavior is unchanged until a language issue registers a lane.

Issue #811 is the spec of record; all behavioral decisions below restate it,
none are new.

## Approach stance

- **Scope**: mechanism only — scoping, lanes, the shared fix loop, the
  2-attempt cap, the detection ladder + provider binding, checkpoint
  granularity, ordering ahead of semantic reviewers, metrics fold, and the
  `DEV_TEAM_STATIC_SELF_HEAL=off` opt-out. Language tool facts (invocations,
  flags, providers, install scripts) stay with #807–#810; the skeletons carry
  one placeholder per language so each lands into a disjoint region.
- **Format fidelity**: additive edits to `build/SKILL.md` and
  `tool-configs.md`; no existing prose is rewritten beyond the two checkpoint
  bullets the issue names.
- **Mechanism home (inferred, noted for review)**: the full mechanism text
  lives in a new `plugins/dev-team/skills/build/references/static-self-heal.md`
  — it is `/build`'s orchestration mechanism (progressively disclosed at
  checkpoint time), while `static-analysis-integration`'s own SKILL.md
  constraint is "collect and report only; make no code edits", which the
  self-heal loop would contradict if embedded there. The registry and the
  setup guide live exactly where the issue pins them.

## Acceptance Criteria

- [ ] Build SKILL.md sub-steps 4 and 6 document the static self-heal pass
      running before spec-compliance-review at each existing checkpoint, and
      no other build step references it.
- [ ] Scoping is documented as the two-case rule (working-tree-vs-HEAD +
      untracked per-step; `slice_start_sha` for batched), with per-attempt
      re-resolution and the empty-partition-never-dispatched guarantee.
- [ ] The shared fix loop (pre-fix → verify → agent hand-off → 2-attempt cap)
      is specified in exactly one place.
- [ ] The "Build-time lanes" registry section exists in `tool-configs.md`
      with the capability-slot row shape and one placeholder per language
      (Python, JS/TS, C#, Java); zero lanes are registered.
- [ ] All four degradation rungs are documented; none is a failed checkpoint.
- [ ] Escalation after exactly 2 agent-fix attempts, with a root-cause
      diagnosis per the Escalation-section convention.
- [ ] C# post-hoc SARIF filtering and the rebuild-on-stale freshness rule are
      documented in the mechanism.
- [ ] Mixed-language dispatch with independent per-lane attempt counters is
      documented.
- [ ] The metrics fold is documented against sub-step 7's schema.
- [ ] The mechanism lands with zero lanes as a structural no-op.
- [ ] `DEV_TEAM_STATIC_SELF_HEAL=off` skips the pass with one info line.
- [ ] Cross-lane invalidation is documented as no-re-verify.
- [ ] `language-setup.md` exists with the skeleton (intro, opt-out, per-lane
      section contract, `/project-init` pointer) and one placeholder per
      language.
- [ ] Bind-don't-replace, the provider qualification contract (a–d), and the
      slice-boundary demotion rule are stated once, in the mechanism.

## Slices

### Slice 1: Static self-heal mechanism + registry and guide skeletons

**Depends-on:** none
**Files:** `plugins/dev-team/skills/build/SKILL.md`,
`plugins/dev-team/skills/build/references/static-self-heal.md`,
`plugins/dev-team/skills/static-analysis-integration/references/tool-configs.md`,
`plugins/dev-team/skills/static-analysis-integration/references/language-setup.md`,
`plugins/dev-team/skills/static-analysis-integration/SKILL.md`,
`tests/skills/test_build_static_self_heal.py`,
`tests/skills/test_static_analysis_lane_skeletons.py`

**Behavior:**

```gherkin
Feature: Static self-heal pass at /build review checkpoints

  Scenario: Checkpoints run the static pass before semantic review
    Given the build skill's inline review checkpoints (per-step complex and slice-boundary)
    When either checkpoint fires
    Then the skill text orders the static self-heal pass before spec-compliance-review
    And no other build step references the pass

  Scenario: Zero registered lanes is a structural no-op
    Given the Build-time lanes registry contains only per-language placeholders
    When the static self-heal pass resolves lanes for a checkpoint
    Then every language partition matches no registered lane
    And the checkpoint proceeds to semantic review unchanged

  Scenario: Opt-out short-circuits the pass
    Given DEV_TEAM_STATIC_SELF_HEAL=off is set
    When a checkpoint fires
    Then no lane tool probe or invocation occurs
    And one info line notes the skip

  Scenario: A lane with persistent findings escalates after two agent-fix attempts
    Given a lane whose verify keeps reporting findings after agent fixes
    When the third verify still fails
    Then the checkpoint escalates with remaining findings and a one-line root-cause diagnosis

  Scenario: Language issues append into disjoint skeleton regions
    Given the registry and setup guide each carry one placeholder section per language
    When a language issue registers its lane
    Then it edits only its own placeholder in each file
```

**Steps:**

#### Step 1.1: Mechanism reference + build SKILL.md checkpoint wiring

**Complexity**: standard
**RED**: `tests/skills/test_build_static_self_heal.py` — sub-steps 4/6 order
the pass before spec-compliance-review, no other step references it, and the
mechanism doc carries scoping, loop, cap, ladder, binding contract, demotion,
C# accommodation, ordering/context injection, metrics fold, opt-out, and
cross-lane no-re-verify.
**GREEN**: write `skills/build/references/static-self-heal.md`; edit
`skills/build/SKILL.md` sub-steps 4 and 6.
**REFACTOR**: tighten prose; verify no drift into language tool facts.
**Files**: `plugins/dev-team/skills/build/SKILL.md`,
`plugins/dev-team/skills/build/references/static-self-heal.md`,
`tests/skills/test_build_static_self_heal.py`
**Commit**: `feat(build): run static self-heal mechanism at review checkpoints (#811)`

#### Step 1.2: Registry and setup-guide skeletons with four language placeholders

**Complexity**: standard
**RED**: `tests/skills/test_static_analysis_lane_skeletons.py` — tool-configs.md
gains a "Build-time lanes" section (row shape, zero registered lanes, four
placeholders); `language-setup.md` exists with intro, opt-out, section
contract, `/project-init` pointer, four placeholders; SKILL.md Related lists it.
**GREEN**: append the registry section, create `language-setup.md`, add the
Related line.
**REFACTOR**: none expected.
**Files**: `plugins/dev-team/skills/static-analysis-integration/references/tool-configs.md`,
`plugins/dev-team/skills/static-analysis-integration/references/language-setup.md`,
`plugins/dev-team/skills/static-analysis-integration/SKILL.md`,
`tests/skills/test_static_analysis_lane_skeletons.py`
**Commit**: `feat(static-analysis): add build-time lane registry and language-setup skeletons (#811)`

## Parallelization

```mermaid
graph TD
  S1[Slice 1]
```

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Complexity Classification

Both steps are `standard`: documentation/mechanism prose plus pytest content
guards, within existing patterns (tests/skills/ structural sensors).

## Skipped (low value)

- None.

## Pre-PR Quality Gate

- [ ] All tests pass (`python3 -m pytest tests/skills/ -q` and full `bash scripts/ci-local.sh`)
- [ ] `scripts/check_md_references.py` clean (new cross-file links resolve)
- [ ] Zero-lane no-op: no language tool fact appears in mechanism or skeletons

## Risks & Open Questions

- **Mechanism home** is inferred (see Approach stance) — flagged for the
  epic integrator; cheap to relocate before Wave 1 lands since language
  issues never edit the mechanism file.
- #813 also edits `build/SKILL.md`; the epic plan sequences them, and the
  pass binds to checkpoints, not cadence.

## Approval

Auto-approved (non-interactive) at 2026-07-04 — no human review gate. Trigger: no TTY (background build sub-agent for epic #823).

## Build Progress

- [x] Slice 1: Static self-heal mechanism + registry and guide skeletons
  - [x] Step 1.1: Mechanism reference + build SKILL.md checkpoint wiring
  - [x] Step 1.2: Registry and setup-guide skeletons with four language placeholders
