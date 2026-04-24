You are working in the `agentic-security-review` plugin at
/Users/finsterb/_git-os/agentic-dev-team/plugins/agentic-security-review/

Your task: resolve the contradiction between the security-assessment
caller contract ("produce `memory/report-<slug>.md` on disk") and a
subagent-level restriction that sub-agents are told to return findings
as text, not use the Write tool. Today, sub-agents work around the
conflict by materializing the report file via a `Bash` heredoc — which
works, but is a clear sign that the contract is under-specified.

## Evidence

Observed in the 2026-04-24 runs of `/security-assessment` against the
NextGen fleet. Two sub-agents called it out explicitly:

- speedpay-sdk run closing note: "The Write tool is blocked for
  subagent report files — `report-speedpay-sdk.md` was created via
  `Bash` heredoc."
- login-service run closing note: "The `/security-assessment` skill
  guarded the `Write` tool with 'Subagents should return findings as
  text'. I routed the final report write through Python/Bash to
  satisfy the explicit caller contract of producing
  `memory/report-login-service.md`; all other artifacts wrote through
  `Write` without issue."

The explicit mismatch:

- `agents/exec-report-generator.md:228-240` says: "3. Write the
  report" and "5. Write + verify → Write to
  `memory/report-<slug>.md`. Byte-check that the embedded Mermaid
  matches the source file..."
- Somewhere upstream in the skill / subagent dispatch (possibly the
  orchestrator's sub-agent prompt, possibly a tools-frontmatter
  override) the Write tool is restricted in a way that makes
  `memory/report-<slug>.md` materialization require a workaround.

Effect:

- Byte-verification in step 5 of `exec-report-generator.md` becomes
  load-bearing on a Bash `heredoc` round-trip rather than the Write
  tool's content path. That's fragile — shell heredoc escaping of
  backticks and `$` in a report body is a known footgun.
- Sub-agents report it as noise in closing notes rather than
  surfacing it as a bug.

## Fix direction

Pick ONE of the following resolutions — then apply it uniformly.
The two options have different posture tradeoffs; document the
rationale in the PR description.

### Option A — Grant sub-agents narrow Write access for report materialization only

- Identify where the restriction is expressed. If it's in a subagent
  dispatch prompt: add an explicit "The Write tool MAY be used to
  produce `memory/report-<slug>.md` and nothing else — all other
  artifacts return as text."
- If it's in the agent frontmatter (`tools: Read, Write, Glob, Grep`
  vs. `tools: Read, Glob, Grep`): the exec-report-generator agent
  at `agents/exec-report-generator.md:4` already lists Write. Confirm
  the restriction isn't introduced at a higher layer.
- Keep the byte-verification step (the Write tool writes a specific
  file; then step 5 reads it back and verifies Mermaid line-equality).
  This is the preferred shape — Write has well-understood semantics.

### Option B — Move report materialization out of the sub-agent

- The sub-agent returns the report body as plain text (current
  "findings as text" posture).
- The orchestrator (the parent that dispatched the sub-agent) receives
  the text and uses its own Write tool to materialize
  `memory/report-<slug>.md`.
- Byte-verification runs in the orchestrator, not the sub-agent.
- Pro: stronger isolation boundary. Con: the orchestrator must now
  know the expected file path per-slug, which is extra coupling.

## Acceptance (applies to either option)

- [ ] No sub-agent closing note across any future run contains a
  phrase like "Write tool blocked" or "via Bash heredoc" for the
  report artifact. Smoke-test with a fresh run against
  `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/ivr`
  and grep `memory/audit-ivr.jsonl` + the sub-agent return text.
- [ ] The byte-verification step in
  `agents/exec-report-generator.md:240` still runs and still fails
  closed if the produced Mermaid does not match the source file.
- [ ] The subagent-prompt or agent-frontmatter change is documented
  in `CHANGELOG.md` and in the relevant skill/agent file's "change
  log" footer (if present).
- [ ] If you pick Option A: all other artifacts (findings.jsonl,
  disposition.json, narratives.md, compliance.json,
  service-comm.mermaid) continue to go through whatever mechanism
  is currently working. Do NOT expand the Write allowance beyond
  the specific report file.
- [ ] If you pick Option B: the orchestrator fails fast and loud if
  the sub-agent returns text that doesn't parse as a valid report
  (per the existing report contract in `agents/exec-report-
  generator.md`). Silent passthrough is worse than the heredoc
  workaround.

## Non-goals

- Do NOT rework the report contract (header disclaimer, sections 0-6,
  Top 3 Actions, etc.). That's the orchestrator's definition and is
  working.
- Do NOT let sub-agents use Write unrestrictedly. The
  "findings as text" posture is there for a reason — isolate the
  sub-agent's side effects to what the orchestrator verifies. The
  narrow exemption (Option A) or handoff (Option B) should preserve
  that intent.
- Do NOT change the other subagent return paths (findings.jsonl,
  disposition.json, etc.) unless the chosen option forces it.

## Validation

- Re-run `/security-assessment` against at least two repos after the
  fix — one small (`ivr`) and one large (`speedpay-sdk`). Confirm:
  - `memory/report-<slug>.md` is produced.
  - `memory/audit-<slug>.jsonl` has the expected phase-end events.
  - No "heredoc" or "Write blocked" mentions in sub-agent return
    text.
  - The exec-report Mermaid byte-check still fires (introduce a
    deliberate mismatch for one test and confirm the pipeline fails).

## Definition of done

- PR against the `agentic-security-review` plugin.
- Both validation runs are clean.
- `CHANGELOG.md` entry describing the chosen resolution (Option A
  or Option B) and why.
