# Spec: Resolve sub-agent vs. report-file Write contract contradiction

Source prompt: [`.prompts/security-review-subagent-report-write-contract.md`](../../.prompts/security-review-subagent-report-write-contract.md)
Target plugin: `plugins/agentic-security-review/`

## Intent Description

The security-assessment caller contract requires that a report be materialized to `memory/report-<slug>.md` on disk, and `exec-report-generator` step 5 then byte-verifies that the report's embedded Mermaid matches the source file. Upstream of the agent, the sub-agent dispatch prompt (or similar layer) tells sub-agents to "return findings as text" and treats the `Write` tool as restricted. Sub-agents resolve the conflict by producing the report via a `Bash` heredoc — which works but is fragile (heredoc escaping of backticks and `$` in a report body is a known footgun) and masks the contract mismatch by surfacing it as a closing-note complaint rather than as a bug.

This change resolves the contradiction by choosing one of two documented resolutions and applying it uniformly. Option A grants sub-agents narrow `Write` access solely for the report file; Option B moves report materialization to the orchestrator. Either is valid; the PR description must document the rationale for the choice. After the fix, no future run may report "Write tool blocked" or "via Bash heredoc" for the report artifact, and the byte-verification step must continue to fire closed on Mermaid mismatches.

## User-Facing Behavior

```gherkin
Feature: Sub-agent report materialization without Write-tool contradiction

  Scenario: Sub-agent produces the report without a heredoc workaround (Option A)
    Given the subagent-prompt grants narrow Write access for memory/report-<slug>.md only
    When the exec-report-generator sub-agent runs during /security-assessment
    Then the report is written directly via the Write tool
    And no sub-agent closing note contains "Write tool blocked"
    And no sub-agent closing note contains "via Bash heredoc"

  Scenario: Sub-agent returns report body as text and orchestrator writes it (Option B)
    Given the subagent returns the report body as plain text
    When the orchestrator receives the sub-agent's return text
    Then the orchestrator writes memory/report-<slug>.md via the Write tool
    And the orchestrator runs the byte-verification step against the written file

  Scenario: Byte-verification fails closed on Mermaid mismatch
    Given a report where the embedded Mermaid diagram diverges from memory/service-comm-<slug>.mermaid
    When exec-report-generator step 5 runs byte-verification
    Then the pipeline fails with a diagnostic identifying the mismatch
    And memory/report-<slug>.md is flagged as invalid

  Scenario: Other artifacts continue using their current mechanism (Option A)
    Given Option A has been applied
    When sub-agents produce findings.jsonl, disposition.json, narratives.md, compliance.json, or service-comm.mermaid
    Then those artifacts flow through the existing mechanism unchanged
    And the Write allowance is not expanded beyond memory/report-<slug>.md

  Scenario: Orchestrator fails fast if sub-agent returns malformed text (Option B)
    Given Option B has been applied
    And the sub-agent returns text that does not parse as a valid report per exec-report-generator's contract
    When the orchestrator receives the text
    Then the orchestrator fails fast with a clear diagnostic
    And no file is written
    And the failure is not silently swallowed

  Scenario: Smoke test against a small and a large repo produces report files cleanly
    Given the chosen resolution has been applied
    When /security-assessment runs against spnextgen/ivr and speedpay-sdk
    Then memory/report-ivr.md and memory/report-speedpay-sdk.md are produced
    And memory/audit-ivr.jsonl and memory/audit-speedpay-sdk.jsonl contain the expected phase-end events
    And neither run's sub-agent return text mentions "heredoc" or "Write blocked"

  Scenario: Changelog and file-level change log reflect the chosen resolution
    Given the PR is merged
    Then CHANGELOG.md records which option (A or B) was chosen and why
    And the relevant skill / agent file's "change log" footer (if present) records the change
```

## Architecture Specification

**The two options are mutually exclusive and equally valid.** The PR description must justify the choice.

**Option A — Narrow Write allowance for sub-agents**

- Components modified:
  - The subagent-dispatch prompt or agent frontmatter layer that currently restricts `Write`. Locate the restriction first — the exec-report-generator's own frontmatter at `agents/exec-report-generator.md:4` already lists `Write`, so the restriction is introduced at a higher layer.
  - Insert: "The Write tool MAY be used to produce `memory/report-<slug>.md` and nothing else — all other artifacts return as text."
- Trust boundary: unchanged for every non-report artifact. The exception is scoped to one specific file name pattern.
- Byte-verification location: unchanged — still executes in the sub-agent per `agents/exec-report-generator.md:240`.

**Option B — Move materialization to the orchestrator**

- Components modified:
  - Sub-agent dispatch path: sub-agent returns the report body as plain text (current "findings as text" posture).
  - Orchestrator (the parent dispatcher): receives the text and writes `memory/report-<slug>.md` via its own `Write` tool.
  - `agents/exec-report-generator.md` step 5: byte-verification moves from the sub-agent to the orchestrator.
- Trust boundary: stronger — sub-agent has no filesystem write at all for the report.
- Coupling cost: the orchestrator must now know the expected file path per-slug.

**Components NOT modified (either option)**

- The report contract itself (header disclaimer, sections 0-6, Top 3 Actions). The orchestrator's definition is working.
- Other subagent return paths (findings.jsonl, disposition.json, narratives.md, compliance.json, service-comm.mermaid) unless the chosen option forces it.
- The "findings as text" posture beyond the narrow exemption or handoff.

**Constraints**

- Sub-agents may NOT receive unrestricted `Write` access. The "findings as text" posture exists for isolation; the resolution must preserve that intent.
- The byte-verification step (step 5 of `exec-report-generator.md`) is load-bearing and must continue to fire closed on Mermaid mismatches regardless of which option is chosen.
- If Option B is chosen, the orchestrator must fail fast on malformed return text — silent passthrough is worse than the heredoc workaround.
- Changelog entry must document the chosen option and its rationale.

## Acceptance Criteria

- [ ] PR description documents whether Option A or Option B was chosen and why.
- [ ] The chosen option is applied uniformly — no partial applications or mixed modes.
- [ ] No `/security-assessment` run's sub-agent closing notes contain "Write tool blocked" or "via Bash heredoc" for the report artifact.
- [ ] Smoke test against `spnextgen/ivr`: `memory/report-ivr.md` is produced; `memory/audit-ivr.jsonl` records expected phase-end events; return text contains no "heredoc"/"Write blocked" strings.
- [ ] Smoke test against `speedpay-sdk`: same checks pass.
- [ ] `exec-report-generator.md:240` byte-verification step still runs. A deliberately introduced Mermaid mismatch fails the pipeline.
- [ ] Option A acceptance (if chosen): all other artifacts (findings.jsonl, disposition.json, narratives.md, compliance.json, service-comm.mermaid) continue through their current mechanism; no expansion of Write allowance beyond `memory/report-<slug>.md`.
- [ ] Option B acceptance (if chosen): orchestrator fails fast and loud on sub-agent text that does not parse as a valid report; no silent passthrough.
- [ ] `CHANGELOG.md` entry describes the chosen resolution and reasoning.
- [ ] If the relevant skill or agent file has a "change log" footer, it records this change.
- [ ] CI passes.

## Consistency Gate

- [x] Intent is unambiguous — resolve the contradiction by picking and applying one of two documented options
- [x] Every behavior in the intent has at least one corresponding BDD scenario (both Option A and Option B behaviors, plus byte-verification preservation)
- [x] Architecture specification constrains implementation to what the intent requires
- [x] Concepts named consistently (`memory/report-<slug>.md`, `Write` tool, byte-verification, "findings as text")
- [x] No artifact contradicts another

**Open decision**: Option A vs. Option B is not pre-resolved in this spec. Per the specs skill, unresolved decisions may advance to planning only if the plan is explicitly tasked with surfacing the tradeoff for the human to decide. Recommend that `/plan` carry forward the two-option fork rather than silently picking one.

**Verdict: PASS (with decision to surface at plan time)** — spec is ready for planning; plan must present Option A vs. Option B with tradeoffs so the human picks before implementation begins.
