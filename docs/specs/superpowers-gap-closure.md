# Spec: Superpowers Gap Closure

Closes gaps identified in the [competitive analysis](../../reports/competitive-analysis-2026-04-15.md) against [obra/superpowers](https://github.com/obra/superpowers). Seven core implementation slices (A-G) plus three platform support slices (H1-H3). Multi-platform research document at [docs/specs/multi-platform-support-suggestions.md](multi-platform-support-suggestions.md).

## Dependency Graph

```
A (anti-rationalization knowledge)
├── F (TDD skill depth) — cross-references A's knowledge file
E (subagent status codes + prompt templates)
├── G (worktree setup) — uses BLOCKED status + implementer.md
B (code review reception) — independent
C (skill authoring enhancements) — independent (touches agent-eval)
D (debugging supporting files) — independent
H1 (Windows hooks) — independent
H2 (Gemini CLI support) — independent
H3 (OpenAI Codex support) — independent
```

## Cross-Slice Notes

- **Canonical term**: "anti-rationalization" is the standard term across all slices. Do not use "rationalization prevention" or "rationalization bulletproofing" as synonyms — those are technique names within the concept.
- **Merge targets**: `knowledge/agent-registry.md` and `CLAUDE.md` are modified by multiple slices (A, B, D, E, F, G). Implement in dependency order to avoid merge conflicts.
- **Implementer prompt cross-deps**: Slice E creates `prompts/implementer.md`. Slice F's testing-anti-patterns reference should be mentioned in the implementer prompt. Slice G adds worktree setup to the implementer prompt. Implement E → F's implementer reference → G.

---

## Slice A: Anti-Rationalization Knowledge

### Intent Description

Create a shared knowledge file that catalogs LLM anti-rationalization patterns — the plausible excuses agents generate to skip hard steps across all skills. Currently, the TDD skill and systematic-debugging skill each have their own rationalization tables, but other skills (Quality Gate Pipeline, verification evidence, code review) lack this defense. The knowledge file becomes a reusable reference that any skill can point to, and the existing TDD/debugging tables remain in place as domain-specific supplements that the knowledge file cross-references by link.

This slice modifies only the Quality Gate Pipeline skill — adding an anti-rationalization reference to the existing Phase 2 "Red Flag Language" block. The TDD skill cross-reference is Slice F's responsibility.

### User-Facing Behavior

```gherkin
Feature: Anti-rationalization knowledge file

  Scenario: Agent encounters rationalization during TDD
    Given an agent is following the TDD skill
    When the agent generates an excuse to skip writing a test first
    Then the excuse matches a pattern in the anti-rationalization knowledge file
    And the agent recognizes it as rationalization and restarts from RED

  Scenario: Agent encounters rationalization during quality gate
    Given an agent is running the Quality Gate Pipeline Phase 2
    When the agent generates red-flag language like "should work now" or "I believe"
    Then the agent detects the language as an anti-rationalization signal
    And the agent pauses to verify before claiming completion

  Scenario: New skill references anti-rationalization knowledge
    Given a developer is authoring a new skill
    When the skill has steps that agents commonly skip
    Then the developer can reference the anti-rationalization knowledge file
    And add domain-specific rationalizations to a table within the new skill

  Scenario: Anti-rationalization knowledge covers cross-cutting patterns
    Given the anti-rationalization knowledge file exists
    Then it contains at minimum these categories:
      | category                    |
      | Skipping verification       |
      | Skipping tests              |
      | Scope expansion             |
      | Premature completion claims |
      | Process shortcuts           |
    And each pattern includes the excuse text and a reality counter

  Scenario: Unlisted rationalization is still caught
    Given the anti-rationalization knowledge file exists
    When an agent generates an excuse not explicitly listed
    Then the catch-all rule applies: "If the excuse isn't listed here, it's still an excuse"
    And the agent treats it as rationalization and follows the skill's restart protocol

  Scenario: Knowledge file cross-references domain-specific tables
    Given the anti-rationalization knowledge file exists
    Then it links to the TDD skill's rationalization table for test-specific patterns
    And it links to the systematic-debugging skill's rationalization table for debugging-specific patterns
    And it does NOT duplicate those tables' contents
```

### Architecture Specification

**Components affected**:
- New file: `plugins/agentic-dev-team/knowledge/anti-rationalization.md`
- Modified: `plugins/agentic-dev-team/skills/quality-gate-pipeline/SKILL.md` — add anti-rationalization reference to the existing Phase 2 "Red Flag Language" block (lines 99-101) and to the Phase 1 "Hallucination Detection Signals" section
- Modified: `plugins/agentic-dev-team/knowledge/agent-registry.md` — register the new knowledge file

**Interfaces**: The knowledge file is a passive reference document. Skills reference it with a markdown link. Agents load it on demand when they need to cross-check excuses.

**Constraints**:
- Do NOT duplicate the existing TDD or systematic-debugging rationalization tables into the knowledge file. Those tables are domain-specific and stay where they are. The knowledge file covers cross-cutting patterns only and links to those tables.
- Keep the file under 600 tokens — it's loaded on demand but should stay lean.
- Do NOT create a "new Red Flag Language section" — add the reference to the existing block.

**Dependencies**: None — pure documentation addition.

### Acceptance Criteria

- [ ] `knowledge/anti-rationalization.md` exists with at least 5 categories of rationalization patterns
- [ ] Each pattern has: excuse text, reality counter, which skills it commonly appears in
- [ ] Knowledge file includes a catch-all statement at the top: "If the excuse isn't listed here, it's still an excuse"
- [ ] Knowledge file cross-references TDD and debugging tables by link rather than duplicating their patterns
- [ ] `quality-gate-pipeline/SKILL.md` existing Phase 2 "Red Flag Language" block references the knowledge file
- [ ] `quality-gate-pipeline/SKILL.md` Phase 1 "Hallucination Detection Signals" references the knowledge file
- [ ] `knowledge/agent-registry.md` includes the new file in the Knowledge Files table
- [ ] The knowledge file is under 600 tokens
- [ ] Existing TDD and debugging rationalization tables are NOT modified (Slice F handles TDD cross-ref)

---

## Slice B: Code Review Reception Skill

### Intent Description

Create a new skill that defines behavioral constraints for how agents respond to code review feedback — whether from `/code-review`, `/apply-fixes`, or human reviewers. Currently, agents blindly accept all review findings and implement every suggestion without critical evaluation. This is a known LLM failure mode: performative agreement ("You're absolutely right!") followed by uncritical implementation of suggestions that may be wrong, unnecessary, or scope-expanding. The skill enforces technical verification before implementing any suggestion, mandates reasoned pushback when a suggestion would make the code worse, and includes a YAGNI gate to prevent gold-plating in response to reviews.

Human feedback has higher authority than agent-generated feedback — the agent can push back with reasoning but defers to the human's final decision after one round. Tone is concise for both audiences.

### User-Facing Behavior

```gherkin
Feature: Code review reception discipline

  Scenario: Agent receives a valid review finding
    Given an agent has received code review feedback
    And the finding is technically correct and addresses a real issue
    When the agent evaluates the finding
    Then the agent verifies the finding against the actual code
    And implements the fix with verification evidence

  Scenario: Agent receives an incorrect review finding
    Given an agent has received code review feedback
    And the finding is technically incorrect or based on a misunderstanding
    When the agent evaluates the finding
    Then the agent states why the finding is incorrect with specific code references
    And does NOT implement the suggested change
    And does NOT use performative agreement language

  Scenario: Agent receives a valid but YAGNI suggestion
    Given an agent has received code review feedback
    And the finding suggests adding capability beyond current requirements
    When the agent evaluates the finding
    Then the agent identifies it as scope expansion
    And declines to implement with a YAGNI justification
    And logs the suggestion for future consideration

  Scenario: Agent receives a subjective style preference
    Given an agent has received code review feedback
    And the finding is a style preference not backed by project conventions
    When the agent evaluates the finding
    Then the agent checks project conventions and linting rules
    And only implements if a convention or rule supports the change

  Scenario: Performative agreement language is blocked
    Given an agent is about to respond to code review feedback
    When the agent drafts a response containing phrases like:
      | phrase                      |
      | You're absolutely right     |
      | Great catch                 |
      | Of course, I should have    |
      | That's a good point         |
    Then the agent replaces the performative language
    And responds with technical evaluation only

  Scenario: Agent verifies before implementing any suggestion
    Given an agent has received a review suggestion to change code
    When the agent decides to implement the suggestion
    Then the agent first reads the relevant code to verify the issue exists
    And confirms the suggested fix would not introduce regressions
    And only then applies the change

  Scenario: Agent receives feedback from a human reviewer
    Given an agent has received code review feedback from a human
    And the agent believes the feedback is incorrect
    When the agent evaluates the finding
    Then the agent states its technical reasoning concisely
    And defers to the human's final decision after one round of pushback

  Scenario: Agent receives ambiguous feedback
    Given an agent has received code review feedback
    And the finding is ambiguous — neither clearly correct nor clearly incorrect
    When the agent evaluates the finding
    Then the agent escalates the ambiguous finding to the human for clarification
    And does NOT guess at the reviewer's intent
```

### Architecture Specification

**Components affected**:
- New file: `plugins/agentic-dev-team/skills/receiving-code-review/SKILL.md`
- Modified: `plugins/agentic-dev-team/knowledge/agent-registry.md` — register the new skill
- Modified: `plugins/agentic-dev-team/CLAUDE.md` — add to skills quick reference count and skills-by-phase table (Review phase)

**Interfaces**: This skill is behavioral — loaded by any agent that receives review feedback. Primary consumer contexts (agents running within these commands load the skill):
- The `/apply-fixes` command
- The implementer subagent (receives inline review checkpoint results during `/build`)
- Any agent in a Phase 3 review-correction loop

No modifications to those commands are needed — they are listed as consumer contexts, not files to edit.

**Constraints**:
- The skill is behavioral only — it constrains how agents respond to feedback, it does not modify review output format or review agent behavior
- It must not conflict with the Quality Gate Pipeline Phase 3 review-correction loop. That loop says "fix critical/major defects." This skill adds: "but verify each finding is real before fixing it"
- Keep under 500 tokens — it's a discipline skill, not a technique manual

**Dependencies**: Quality Gate Pipeline (Phase 3 review-correction loop)

### Acceptance Criteria

- [ ] `skills/receiving-code-review/SKILL.md` exists with frontmatter
- [ ] Skill includes a banned-phrases list for performative agreement
- [ ] Skill includes a verification-before-implementation gate
- [ ] Skill includes a YAGNI gate for scope-expanding suggestions
- [ ] Skill includes a rationalization prevention table (agents rationalize agreeing too, not just skipping)
- [ ] Skill distinguishes human feedback (higher authority, defer after one pushback) from agent feedback (full technical challenge)
- [ ] Skill includes guidance for ambiguous findings: escalate to human, don't guess
- [ ] Tone guidance: concise technical evaluation for both audiences, no emotional language
- [ ] `knowledge/agent-registry.md` includes the new skill
- [ ] `CLAUDE.md` quick reference updated with skill count and skills-by-phase table
- [ ] Skill is under 500 tokens
- [ ] Skill does not conflict with Quality Gate Pipeline Phase 3

---

## Slice C: Skill Authoring Enhancements (Pressure Testing + CSO)

### Intent Description

Enhance the existing `agent-skill-authoring` skill with two additions drawn from superpowers' `writing-skills` methodology. First, **pressure testing** — a structured process for testing whether a skill's instructions hold up under adversarial conditions (the agent is deep in implementation, eager to deliver, and generating rationalizations). Pressure scenarios are saved as eval fixtures and integrated into `/agent-eval`. Second, **Claude Search Optimization (CSO)** refinement — the existing skill already has guidance about description optimization, but this needs strengthening with concrete examples and a pass/fail checklist.

### User-Facing Behavior

```gherkin
Feature: Skill authoring pressure testing and description optimization

  Scenario: Author pressure-tests a new skill
    Given a developer has written a new skill
    When the developer follows the skill authoring guide
    Then the guide instructs them to run the task WITHOUT the skill first
    And observe natural failure modes
    And write pressure scenarios that probe each failure mode
    And verify the skill prevents each failure when loaded

  Scenario: Pressure scenario catches a skill weakness
    Given a skill has been written with constraints
    And a pressure scenario simulates an agent rationalizing around a constraint
    When the pressure scenario is executed
    Then the skill either prevents the rationalization or the weakness is identified
    And the author strengthens the skill to close the gap

  Scenario: Pressure scenarios are saved as eval fixtures
    Given a developer has written pressure scenarios for a skill
    When the developer follows the authoring guide
    Then the scenarios are saved in the evals directory alongside agent eval fixtures
    And each scenario specifies the skill, the adversarial condition, and expected behavior

  Scenario: agent-eval runs pressure scenarios against skills
    Given pressure scenario fixtures exist for a skill
    When the user runs /agent-eval
    Then the eval framework executes each pressure scenario
    And reports whether the skill prevented the adversarial behavior

  Scenario: Malformed pressure fixture is reported
    Given a pressure scenario fixture exists but has invalid format
    When the user runs /agent-eval
    Then the eval framework reports a parse error for the malformed fixture
    And identifies which fixture file failed and what is wrong with it

  Scenario: Skill description follows CSO guidelines
    Given a developer is writing a skill description
    When the developer follows the authoring guide
    Then the description contains ONLY triggering conditions
    And the description does NOT summarize the skill's workflow or steps
    And the description does NOT list the skill's internal structure

  Scenario: CSO checklist catches a bad description
    Given a skill has a description that summarizes its workflow
    When the author runs the CSO checklist
    Then the checklist flags the description as problematic
    And suggests rewriting to focus on when/why to trigger
```

### Architecture Specification

**Components affected**:
- Modified: `plugins/agentic-dev-team/skills/agent-skill-authoring/SKILL.md` — expand "Apply TDD to skill-writing itself" into a pressure testing procedure and strengthen "Optimize skill descriptions for triggering" into a CSO checklist
- Modified: `plugins/agentic-dev-team/commands/agent-eval.md` — add pressure scenario fixture support alongside agent eval fixtures
- Fixture location: `evals/pressure/` directory, alongside existing `evals/` fixtures

**Interfaces**: No new interfaces. The authoring skill is consumed by anyone authoring skills. The eval command gains a new fixture type.

**Constraints**:
- The existing skill already has the "Apply TDD to skill-writing itself" and "Optimize skill descriptions for triggering" sections. Enhance these in place — do not create parallel sections.
- Keep total skill file under 1,200 tokens (currently ~990 tokens per registry)
- Do not add a separate knowledge file for this — the guidance belongs inline in the authoring skill

**Dependencies**: None for the skill edit. The eval integration depends on the existing `/agent-eval` command structure.

### Acceptance Criteria

- [ ] "Apply TDD to skill-writing itself" section expanded with a concrete pressure testing procedure: (1) run without skill, (2) catalog failure modes, (3) write pressure scenarios, (4) verify skill prevents each failure
- [ ] At least 3 example pressure scenarios included as templates (e.g., "agent is 80% through implementation and wants to skip the verification step")
- [ ] Pressure scenario fixture format defined (skill name, adversarial condition, expected agent behavior, pass/fail criteria)
- [ ] Fixtures saved to `evals/pressure/` directory
- [ ] `commands/agent-eval.md` updated to mention skill pressure scenarios alongside agent eval fixtures
- [ ] Eval framework reports parse errors for malformed pressure fixtures
- [ ] "Optimize skill descriptions for triggering" expanded into a CSO checklist with pass/fail criteria
- [ ] CSO checklist includes at least 2 "good" and 2 "bad" description examples
- [ ] Total skill file stays under 1,200 tokens
- [ ] `knowledge/agent-registry.md` updated if `/agent-eval` description changes

---

## Slice D: Systematic Debugging Supporting Files

### Intent Description

Add three supporting reference files to the systematic-debugging skill directory that provide concrete, reusable techniques agents can load on demand during debugging. Currently, the skill defines a solid 4-phase process but is procedural — it tells agents *what* to do (investigate, trace, hypothesize) without providing detailed *how-to* techniques. We'll add the three highest-value ones: root-cause tracing (backward call-chain analysis), condition-based waiting (replacing arbitrary sleeps/timeouts in tests with polling), and a test polluter finder (language-agnostic bisection algorithm for identifying which test pollutes shared state).

### User-Facing Behavior

```gherkin
Feature: Systematic debugging supporting reference files

  Scenario: Agent uses root-cause tracing during investigation
    Given an agent is in Phase 2 (Investigate) of systematic debugging
    And the failure involves a value that is wrong at the point of use
    When the agent loads the root-cause-tracing reference
    Then the agent traces backward through the call chain from symptom to origin
    And identifies the layer where the value first diverges from expected

  Scenario: Agent replaces arbitrary timeout with condition-based waiting
    Given an agent is debugging a flaky test
    And the test uses sleep or setTimeout to wait for an async condition
    When the agent loads the condition-based-waiting reference
    Then the agent replaces the arbitrary wait with a polling pattern
    And the polling pattern has a timeout ceiling and descriptive error on timeout

  Scenario: Agent identifies a test polluter
    Given an agent is debugging a test that passes in isolation but fails in suite
    And the failure is caused by shared state pollution from another test
    When the agent loads the find-polluter reference
    Then the agent uses bisection to identify which prior test pollutes the state
    And the bisection narrows to the specific polluting test

  Scenario: Supporting files are loaded on demand only
    Given the systematic-debugging skill is loaded
    When the agent enters Phase 2 and needs a specific technique
    Then only the relevant supporting file is loaded
    And other supporting files remain unloaded to conserve context
```

### Architecture Specification

**Components affected**:
- New file: `plugins/agentic-dev-team/skills/systematic-debugging/root-cause-tracing.md`
- New file: `plugins/agentic-dev-team/skills/systematic-debugging/condition-based-waiting.md`
- New file: `plugins/agentic-dev-team/skills/systematic-debugging/find-polluter.md`
- Modified: `plugins/agentic-dev-team/skills/systematic-debugging/SKILL.md` — add "Supporting References" section in Phase 2 that links to the three files with guidance on when to load each
- Modified: `plugins/agentic-dev-team/knowledge/agent-registry.md` — note the supporting files exist under the skill entry

**Interfaces**: Supporting files are passive markdown references loaded by the agent on demand. The main SKILL.md links to them with triggering conditions (e.g., "Load root-cause-tracing.md when the failure involves a wrong value at the point of use").

**Constraints**:
- Each supporting file should be under 400 tokens — they're technique references, not full skills
- The `find-polluter.md` describes the bisection algorithm in language-agnostic terms, not an executable script (projects use different test runners)
- Do not restructure the existing 4-phase process — the supporting files augment Phase 2, they don't replace it

**Dependencies**: Systematic Debugging skill (existing)

### Acceptance Criteria

- [ ] `skills/systematic-debugging/root-cause-tracing.md` exists with backward tracing technique
- [ ] `skills/systematic-debugging/condition-based-waiting.md` exists with polling pattern replacing arbitrary waits
- [ ] `skills/systematic-debugging/find-polluter.md` exists with language-agnostic bisection algorithm
- [ ] Each supporting file is under 400 tokens
- [ ] Main `SKILL.md` Phase 2 section includes a "Supporting References" block linking to each file with when-to-load guidance
- [ ] `knowledge/agent-registry.md` updated to note supporting files
- [ ] `find-polluter.md` is language-agnostic (describes algorithm, not a shell script)
- [ ] Existing 4-phase process is unchanged

---

## Slice E: Subagent Status Codes

### Intent Description

Introduce a structured 4-status-code protocol for subagent reporting: `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, and `BLOCKED`. Currently, subagents return free-form text and the orchestrator must parse success/failure from unstructured output. This slice adds clear, parseable signals for subagent outcomes and creates the three missing prompt templates (`implementer.md`, `spec-reviewer.md`, `quality-reviewer.md`) with full behavioral content. The four existing plan review templates are also updated to adopt the status protocol.

The status protocol uses two output formats depending on template type:
- **Markdown status block**: Used by implementer, spec-reviewer, and quality-reviewer (new templates)
- **JSON `"status"` field**: Used by plan review templates (existing JSON output format, `"status"` added alongside existing `"verdict"`)

### User-Facing Behavior

```gherkin
Feature: Subagent structured status codes

  Scenario: Subagent completes work successfully
    Given the orchestrator has dispatched a subagent for a task
    When the subagent finishes the work and all verification passes
    Then the subagent returns status DONE
    And includes verification evidence in its response

  Scenario: Subagent completes with reservations
    Given the orchestrator has dispatched a subagent for a task
    When the subagent finishes the work but has concerns about the approach
    Then the subagent returns status DONE_WITH_CONCERNS
    And includes the completed work plus a list of specific concerns
    And the orchestrator reviews the concerns before accepting the work

  Scenario: Orchestrator handles DONE_WITH_CONCERNS
    Given a subagent returned DONE_WITH_CONCERNS with a list of concerns
    When the orchestrator receives the status
    Then the orchestrator evaluates each concern
    And decides per-concern: accept the work as-is, re-dispatch with guidance, or escalate to user
    And logs the decision for each concern

  Scenario: Subagent needs more context from parent
    Given the orchestrator has dispatched a subagent for a task
    When the subagent cannot complete because it lacks information
    And the missing information is available in the parent context
    Then the subagent returns status NEEDS_CONTEXT
    And specifies exactly what information is needed
    And the orchestrator re-dispatches with the additional context

  Scenario: Subagent is blocked by an external dependency
    Given the orchestrator has dispatched a subagent for a task
    When the subagent cannot proceed due to an unresolvable dependency
    Then the subagent returns status BLOCKED
    And describes the blocking dependency
    And the orchestrator escalates to the user

  Scenario: Orchestrator handles NEEDS_CONTEXT with re-dispatch
    Given a subagent returned NEEDS_CONTEXT requesting file contents
    When the orchestrator receives the status
    Then the orchestrator gathers the requested context
    And re-dispatches the same subagent prompt with added context
    And does NOT treat NEEDS_CONTEXT as a failure

  Scenario: Orchestrator handles BLOCKED with user escalation
    Given a subagent returned BLOCKED citing an external service dependency
    When the orchestrator receives the status
    Then the orchestrator presents the blocker to the user
    And pauses the task until the user provides direction

  Scenario: NEEDS_CONTEXT re-dispatch is capped
    Given a subagent has returned NEEDS_CONTEXT twice for the same task
    When the subagent returns NEEDS_CONTEXT a third time
    Then the orchestrator escalates to the user instead of re-dispatching
    And reports what context was requested across all three attempts

  Scenario: Orchestrator receives unrecognized status
    Given a subagent returns a status code not in the protocol
    When the orchestrator parses the response
    Then the orchestrator treats the unrecognized status as BLOCKED
    And escalates to the user with the raw subagent output

  Scenario: Plan reviewer returns status via JSON
    Given the orchestrator dispatches a plan review subagent
    When the reviewer completes its review
    Then the JSON output includes both "verdict" and "status" fields
    And the mapping is:
      | verdict         | warnings | status              |
      | approve         | 0        | DONE                |
      | approve         | 1+       | DONE_WITH_CONCERNS  |
      | needs-revision  | any      | DONE_WITH_CONCERNS  |
```

### Architecture Specification

**Components affected**:
- Modified: `plugins/agentic-dev-team/agents/orchestrator.md` — add "Subagent Status Protocol" section defining the 4 codes, orchestrator response table, and two output formats
- New file: `plugins/agentic-dev-team/prompts/implementer.md` — full implementer behavioral content + markdown status block
- New file: `plugins/agentic-dev-team/prompts/spec-reviewer.md` — full spec review behavioral content + markdown status block
- New file: `plugins/agentic-dev-team/prompts/quality-reviewer.md` — full quality review behavioral content + markdown status block
- Modified: `plugins/agentic-dev-team/prompts/plan-review-acceptance.md` — add `"status"` field to JSON output
- Modified: `plugins/agentic-dev-team/prompts/plan-review-design.md` — add `"status"` field to JSON output
- Modified: `plugins/agentic-dev-team/prompts/plan-review-ux.md` — add `"status"` field to JSON output
- Modified: `plugins/agentic-dev-team/prompts/plan-review-strategic.md` — add `"status"` field to JSON output
- Modified: `plugins/agentic-dev-team/commands/build.md` — update step 4 to handle NEEDS_CONTEXT and BLOCKED status from subagents
- Modified: `plugins/agentic-dev-team/CLAUDE.md` — update "Multi-Agent Collaboration Protocol" to reference the status protocol
- Modified: `plugins/agentic-dev-team/knowledge/agent-registry.md` — update prompt template entries

**Interfaces**:

Markdown status block (new templates):
```
## Status
**Result**: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
**Concerns**: [list, if DONE_WITH_CONCERNS]
**Needs**: [specific info needed, if NEEDS_CONTEXT]
**Blocker**: [description, if BLOCKED]
```

JSON status field (plan review templates — added to existing output):
```json
{
  "reviewer": "plan-review-*",
  "verdict": "approve | needs-revision",
  "status": "DONE | DONE_WITH_CONCERNS",
  ...
}
```

Orchestrator response table:
| Status | Orchestrator action |
|--------|-------------------|
| DONE | Accept work, proceed |
| DONE_WITH_CONCERNS | Review concerns, decide: accept / re-dispatch with guidance / escalate |
| NEEDS_CONTEXT | Gather info, re-dispatch (max 2 re-dispatches before escalating) |
| BLOCKED | Escalate to user immediately |
| Unrecognized | Treat as BLOCKED, escalate with raw output |

**Constraints**:
- NEEDS_CONTEXT re-dispatch has a max of 2 attempts — after that, escalate to user
- The two output formats (markdown block and JSON field) are both documented in the orchestrator's status protocol section
- This does not change model routing — status codes are orthogonal to model selection
- Plan review templates keep their existing `"verdict"` field — `"status"` is additive

**Dependencies**: Orchestrator agent, build command, all subagent prompt templates

### Acceptance Criteria

- [ ] Orchestrator agent has a "Subagent Status Protocol" section defining all 4 codes
- [ ] Orchestrator response table maps each status to a concrete action, including unrecognized status
- [ ] `prompts/implementer.md` created with full implementer behavioral content + markdown status block
- [ ] `prompts/spec-reviewer.md` created with full spec review behavioral content + markdown status block
- [ ] `prompts/quality-reviewer.md` created with full quality review behavioral content + markdown status block
- [ ] `prompts/plan-review-acceptance.md` updated with `"status"` JSON field
- [ ] `prompts/plan-review-design.md` updated with `"status"` JSON field
- [ ] `prompts/plan-review-ux.md` updated with `"status"` JSON field
- [ ] `prompts/plan-review-strategic.md` updated with `"status"` JSON field
- [ ] All 7 prompt templates use the documented status format (markdown or JSON as appropriate)
- [ ] `commands/build.md` step 4 handles NEEDS_CONTEXT and BLOCKED
- [ ] CLAUDE.md "Multi-Agent Collaboration Protocol" references the status protocol
- [ ] NEEDS_CONTEXT re-dispatch capped at 2 attempts
- [ ] Both output formats (markdown block + JSON field) documented in orchestrator
- [ ] `knowledge/agent-registry.md` prompt template entries updated

---

## Slice F: TDD Skill Depth

### Intent Description

Deepen the TDD skill with two additions: (1) a "Testing Anti-Patterns" supporting reference file covering common mock/test anti-patterns that agents fall into, and (2) a cross-reference from the existing rationalization table to the anti-rationalization knowledge file (from Slice A). The cross-reference augments the existing catch-all line (currently "If you catch yourself composing an excuse not on this list, it's still an excuse") by adding a link to the knowledge file for cross-cutting patterns.

The testing-anti-patterns reference should also be mentioned in the implementer prompt template (created in Slice E) so subagents have access to it during implementation.

### User-Facing Behavior

```gherkin
Feature: TDD skill depth enhancements

  Scenario: Agent encounters a testing anti-pattern
    Given an agent is writing tests during the RED phase
    When the agent writes a test that mocks a dependency without understanding its contract
    Then the testing-anti-patterns reference identifies this as "mocking without understanding"
    And the agent rewrites the test to use the real dependency or a properly understood fake

  Scenario: Agent encounters mock-tests-mock anti-pattern
    Given an agent is writing a test
    When the test primarily asserts that a mock was called with expected arguments
    Then the testing-anti-patterns reference identifies this as "testing mock behavior"
    And the agent rewrites to test observable outcomes instead of call patterns

  Scenario: Agent falls into sunk cost trap
    Given an agent wrote implementation code before writing a test
    And the agent has invested significant context in the implementation
    When the agent realizes it violated TDD
    Then the sunk cost rationalization entry in the TDD table triggers
    And the agent deletes the implementation and restarts from RED
    And does NOT rationalize keeping the code "as a reference"

  Scenario: TDD skill cross-references anti-rationalization knowledge
    Given the TDD skill's rationalization prevention table exists
    And the anti-rationalization knowledge file exists
    When an agent encounters a rationalization not in the TDD table
    Then the catch-all line directs the agent to the knowledge file for cross-cutting patterns
    And the catch-all rule still applies: the unlisted excuse is still an excuse
```

### Architecture Specification

**Components affected**:
- New file: `plugins/agentic-dev-team/skills/test-driven-development/testing-anti-patterns.md` — supporting reference file
- Modified: `plugins/agentic-dev-team/skills/test-driven-development/SKILL.md` — augment the existing catch-all line with a cross-reference to `knowledge/anti-rationalization.md`, add "Supporting References" section linking to testing-anti-patterns.md
- Modified: `plugins/agentic-dev-team/prompts/implementer.md` (created in Slice E) — mention testing-anti-patterns as a loadable reference during RED phase

**Interfaces**: The testing-anti-patterns file is a passive reference loaded on demand during the RED phase when the agent needs guidance on test quality.

**Constraints**:
- Do NOT duplicate content from the existing rationalization table — add the cross-reference only
- The existing catch-all line at the end of the rationalization table is augmented to: "If you catch yourself composing an excuse not on this list, it's still an excuse. See also [anti-rationalization patterns](../../knowledge/anti-rationalization.md) for cross-cutting patterns beyond TDD."
- The testing-anti-patterns file covers test-writing anti-patterns (mock abuse, test-only methods, testing implementation) — not TDD process violations (those are already in the main skill)
- Keep supporting file under 400 tokens
- The existing SKILL.md already has the Iron Law, 12-entry rationalization table, red flags, and anti-pattern section. Changes should be minimal additions, not rewrites.

**Dependencies**: Slice A (anti-rationalization knowledge file for cross-reference), Slice E (implementer.md creation)

### Acceptance Criteria

- [ ] `skills/test-driven-development/testing-anti-patterns.md` exists with at least 5 anti-patterns
- [ ] Anti-patterns cover: testing mock behavior, test-only production methods, mocking without understanding contract, incomplete mocks, integration tests as afterthought
- [ ] Each anti-pattern has: name, description, why it's harmful, what to do instead
- [ ] Main `SKILL.md` has a "Supporting References" section linking to testing-anti-patterns.md
- [ ] Main `SKILL.md` catch-all line augmented with cross-reference to `knowledge/anti-rationalization.md`
- [ ] `prompts/implementer.md` mentions testing-anti-patterns as a loadable reference
- [ ] Supporting file is under 400 tokens
- [ ] No existing content in the main SKILL.md is duplicated or removed

---

## Slice G: Git Worktree Language-Specific Setup

### Intent Description

Enhance the worktree creation workflow so that after a git worktree is created for a subagent, dependency installation and baseline test verification happen before implementation begins. Currently, `isolation: "worktree"` creates a clean worktree but the subagent starts implementing immediately — if dependencies aren't installed, the first test run fails for the wrong reason (missing deps, not missing feature). This slice adds a setup step to the implementer prompt template.

### User-Facing Behavior

```gherkin
Feature: Git worktree language-specific setup

  Scenario: Worktree setup detects Node.js project
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a package.json
    When the worktree is created
    Then the subagent runs the appropriate install command in the worktree
    And the install command is determined by lock file presence:
      | lock file          | command          |
      | package-lock.json  | npm ci           |
      | yarn.lock          | yarn install     |
      | pnpm-lock.yaml     | pnpm install     |
      | bun.lockb          | bun install      |

  Scenario: Worktree setup detects Python project
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a requirements.txt or pyproject.toml
    When the worktree is created
    Then the subagent installs dependencies in the worktree

  Scenario: Worktree setup detects Go project
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a go.mod
    When the worktree is created
    Then the subagent runs go mod download in the worktree

  Scenario: Worktree setup detects Rust project
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a Cargo.toml
    When the worktree is created
    Then the subagent runs cargo build in the worktree

  Scenario: Worktree setup detects Java Maven project
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a pom.xml
    When the worktree is created
    Then the subagent runs mvn install -DskipTests in the worktree

  Scenario: Worktree setup detects Java Gradle project
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a build.gradle or build.gradle.kts
    When the worktree is created
    Then the subagent runs gradle build -x test in the worktree

  Scenario: Worktree setup detects dotnet project
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a .csproj or .sln file
    When the worktree is created
    Then the subagent runs dotnet restore in the worktree

  Scenario: Worktree setup runs baseline tests
    Given the worktree has been created and dependencies installed
    When the setup step completes
    Then the subagent runs the project's test suite as a baseline
    And verifies all existing tests pass before beginning implementation
    And if baseline tests fail the subagent returns BLOCKED status

  Scenario: Worktree setup for unknown project type
    Given the orchestrator dispatches a subagent with worktree isolation
    And no recognized project files are found
    When the worktree is created
    Then the subagent skips dependency installation
    And proceeds directly to implementation with a warning

  Scenario: Dependency installation fails
    Given the orchestrator dispatches a subagent with worktree isolation
    And the project root contains a package.json
    When the worktree is created
    And the dependency install command fails
    Then the subagent returns BLOCKED status
    And includes the install error output in the blocker description
```

### Architecture Specification

**Components affected**:
- Modified: `plugins/agentic-dev-team/agents/orchestrator.md` — update Phase 3 "Subagent dispatch" section to reference the worktree setup protocol
- Modified: `plugins/agentic-dev-team/prompts/implementer.md` (created in Slice E) — add a "Worktree Setup" section at the top of the implementation flow that runs before RED phase
- New file: `plugins/agentic-dev-team/knowledge/worktree-setup.md` — reference table mapping project indicators to setup commands, loaded by the implementer prompt

**Interfaces**: The worktree setup is a pre-implementation step within the subagent. It is NOT a hook or separate script — it's instructions within the implementer prompt that the subagent follows after the worktree is created but before starting TDD.

**Constraints**:
- The setup step must be fast — install + baseline test should add minimal overhead
- If baseline tests fail, the subagent returns `BLOCKED` (from Slice E's status protocol) rather than attempting to fix pre-existing failures
- If dependency install fails, the subagent returns `BLOCKED` with the error output
- Language detection uses file presence only (package.json, go.mod, etc.) — no heuristics or LLM judgment
- The knowledge file is a simple lookup table, not a decision tree

**Dependencies**: Slice E (subagent status codes — BLOCKED status for baseline/install failures, implementer.md creation)

### Acceptance Criteria

- [ ] `knowledge/worktree-setup.md` exists with a detection table mapping project indicators to install + test commands
- [ ] Detection covers: Node.js (npm/yarn/pnpm/bun), Python, Go, Rust, .NET, Java (Maven/Gradle)
- [ ] `prompts/implementer.md` includes a "Worktree Setup" section that runs before RED
- [ ] Setup runs dependency install then baseline test suite
- [ ] Baseline test failure returns BLOCKED status (not failure, not NEEDS_CONTEXT)
- [ ] Dependency install failure returns BLOCKED status with error output
- [ ] Unknown project type skips setup with a warning
- [ ] `agents/orchestrator.md` Phase 3 references the worktree setup protocol
- [ ] `knowledge/agent-registry.md` updated with the new knowledge file

---

## Slice H1: Windows Hooks Support

### Intent Description

Enable the plugin's 8 bash hooks to work on Windows by adding a cross-platform shim and fixing platform-specific path issues. On Windows, bash is available via Git for Windows (near-universal on dev machines). The approach: keep all hooks as bash scripts, add a `.cmd` wrapper that locates and delegates to bash (same pattern as superpowers), and fix hardcoded `/tmp/`/`$TMPDIR` references. A Windows prerequisite checker (`install.ps1`) replaces `install.sh` for Windows users.

### User-Facing Behavior

```gherkin
Feature: Windows hooks support

  Scenario: Hooks execute on Windows via Git for Windows bash
    Given the plugin is installed on a Windows machine
    And Git for Windows is installed (providing bash.exe on PATH)
    When Claude Code triggers a PreToolUse or PostToolUse hook
    Then the hook command invokes the run-hook.cmd shim
    And the shim locates bash.exe and delegates to the .sh script
    And the hook executes successfully with correct output

  Scenario: Shim locates bash from Git for Windows default path
    Given bash is NOT on the system PATH
    And Git for Windows is installed at the default location
    When run-hook.cmd is invoked
    Then the shim checks "C:\Program Files\Git\bin\bash.exe"
    And uses it to execute the hook script

  Scenario: Shim locates bash from WSL
    Given bash is NOT on the system PATH
    And Git for Windows is NOT installed
    And WSL is available
    When run-hook.cmd is invoked
    Then the shim uses wsl.exe to execute the hook script

  Scenario: Shim fails gracefully when no bash is available
    Given bash is NOT on the system PATH
    And Git for Windows is NOT installed
    And WSL is NOT available
    When run-hook.cmd is invoked
    Then the shim exits with an error message explaining bash is required
    And suggests installing Git for Windows

  Scenario: Hooks use platform-agnostic temp directory
    Given a hook needs a temporary file
    When the hook references a temp directory
    Then it uses ${TMPDIR:-${TEMP:-/tmp}} instead of hardcoded /tmp/
    And the path resolves correctly on both Unix and Windows

  Scenario: Windows prerequisite checker validates environment
    Given a user runs install.ps1 on Windows
    Then the script checks for:
      | prerequisite      | check                          |
      | bash              | bash.exe on PATH or Git for Windows installed |
      | jq                | jq.exe on PATH                 |
      | git               | git.exe on PATH                |
    And reports which prerequisites are missing with install instructions

  Scenario: Hooks work unchanged on macOS and Linux
    Given the plugin is installed on macOS or Linux
    When Claude Code triggers a hook
    Then the hook command invokes bash directly as before
    And the run-hook.cmd shim is not used
    And no behavior changes from the current implementation
```

### Architecture Specification

**Components affected**:
- New file: `plugins/agentic-dev-team/hooks/run-hook.cmd` — Windows shim that locates bash.exe and delegates (~20 lines)
- New file: `plugins/agentic-dev-team/install.ps1` — Windows prerequisite checker
- Modified: `plugins/agentic-dev-team/hooks/tdd-guard.sh` — fix `TMPDIR` reference (use `${TMPDIR:-${TEMP:-/tmp}}`)
- Modified: `plugins/agentic-dev-team/hooks/version-check.sh` — fix hardcoded `/tmp/` path (use `${TMPDIR:-${TEMP:-/tmp}}`)
- Modified: `plugins/agentic-dev-team/settings.json` — document Windows hook invocation pattern

**Interfaces**: The `run-hook.cmd` shim is invoked by Claude Code on Windows instead of `bash` directly. It takes the hook script path as an argument and passes stdin through. Exit codes are preserved.

**Constraints**:
- Do NOT rewrite hooks in PowerShell or Node.js — keep bash, add shim
- Do NOT require WSL — Git for Windows is the primary target
- All 9 existing hooks must continue working unchanged on macOS/Linux
- Only 2 existing `.sh` files are modified (TMPDIR fixes)
- `jq` is a hard dependency — Windows installer must check for it

**Dependencies**: None — independent of all other slices.

### Acceptance Criteria

- [ ] `hooks/run-hook.cmd` exists and locates bash via: (1) PATH, (2) Git for Windows default, (3) WSL
- [ ] Shim exits with clear error if no bash found
- [ ] Shim passes stdin, arguments, and exit codes through correctly
- [ ] `install.ps1` checks for bash, jq, and git on Windows
- [ ] `install.ps1` provides install instructions for each missing prerequisite
- [ ] `tdd-guard.sh` uses `${TMPDIR:-${TEMP:-/tmp}}` instead of hardcoded paths
- [ ] `version-check.sh` uses `${TMPDIR:-${TEMP:-/tmp}}` instead of hardcoded `/tmp/`
- [ ] All 9 hooks pass on macOS/Linux with no behavior change

---

## Slice H2: Gemini CLI Platform Support

### Intent Description

Add Gemini CLI as a supported platform. Gemini CLI has a native extension system with skills (`SKILL.md` with same frontmatter format), agents, hooks (`hooks/hooks.json`), commands (TOML format), and context files (`GEMINI.md`). Our skills and knowledge files are reusable as-is. The approach: create a `gemini-extension.json` manifest and `GEMINI.md` context file, add TOML commands for key workflows, and document capability limitations (no multi-agent orchestration, no model routing, no tool scoping).

### User-Facing Behavior

```gherkin
Feature: Gemini CLI platform support

  Scenario: Plugin is discoverable as a Gemini CLI extension
    Given the plugin repository contains a gemini-extension.json manifest
    When a user installs the extension in Gemini CLI
    Then Gemini CLI loads the manifest and discovers the extension
    And the GEMINI.md context file is loaded into the session

  Scenario: Skills are loaded in Gemini CLI
    Given the plugin is installed as a Gemini CLI extension
    When Gemini CLI scans the skills/ directory
    Then it discovers all SKILL.md files with name and description frontmatter
    And skills are available for implicit and explicit invocation

  Scenario: Knowledge files are accessible
    Given the plugin is installed as a Gemini CLI extension
    When an agent or skill references a knowledge file
    Then the knowledge file is readable as a standard markdown reference

  Scenario: Hooks are loaded from Gemini CLI hooks format
    Given the plugin is installed as a Gemini CLI extension
    And a hooks/hooks-gemini.json file exists
    When Gemini CLI loads hook configuration
    Then compatible hooks execute normally
    And hooks that depend on Claude Code-specific stdin format are skipped with warnings

  Scenario: GEMINI.md provides platform-specific context
    Given the plugin is installed as a Gemini CLI extension
    When a session starts
    Then GEMINI.md is loaded with plugin philosophy, team organization, and skill registry
    And it does NOT reference Claude Code-specific features

  Scenario: Orchestration degrades to inline execution
    Given the plugin is installed in Gemini CLI
    When a multi-agent workflow is triggered
    Then GEMINI.md instructs inline execution as the fallback
    And warns that multi-agent orchestration requires Claude Code

  Scenario: Commands are available as Gemini CLI TOML commands
    Given the plugin is installed as a Gemini CLI extension
    When Gemini CLI scans the commands-gemini/ directory
    Then TOML command files are loaded for key workflows

  Scenario: Agents are loaded with unknown frontmatter ignored
    Given the plugin is installed as a Gemini CLI extension
    When Gemini CLI scans the agents/ directory
    Then agent markdown files are discovered
    And tools: and model: frontmatter fields are ignored without error
```

### Architecture Specification

**Components affected**:
- New file: `plugins/agentic-dev-team/gemini-extension.json`
- New file: `plugins/agentic-dev-team/GEMINI.md`
- New directory: `plugins/agentic-dev-team/commands-gemini/` — TOML commands for key workflows
- New file: `plugins/agentic-dev-team/hooks/hooks-gemini.json`

**Reused as-is**: All `skills/*/SKILL.md`, all `knowledge/*.md`, all `prompts/*.md`

**Constraints**:
- Do NOT fork or duplicate skill files — manifest points to same `skills/` directory
- GEMINI.md is standalone (not symlink to CLAUDE.md)
- Keep TOML command set to top 5 most-used commands initially
- Clearly document capability limitations in GEMINI.md

**Dependencies**: None — independent. Can be implemented in parallel with all other slices.

### Acceptance Criteria

- [ ] `gemini-extension.json` exists with name, version, description, contextFileName
- [ ] `GEMINI.md` exists without Claude Code-specific feature references
- [ ] Skills discoverable from existing `skills/` directory
- [ ] At least 5 TOML commands in `commands-gemini/`
- [ ] `hooks/hooks-gemini.json` defines compatible hooks
- [ ] GEMINI.md documents capability limitations vs Claude Code
- [ ] Existing Claude Code functionality unchanged

---

## Slice H3: OpenAI Codex Platform Support

### Intent Description

Add OpenAI Codex CLI as a supported platform. Codex uses `AGENTS.md` (hierarchical markdown discovery), `SKILL.md` with same frontmatter (skills in `.agents/skills/`), `config.toml`, `hooks.json`, and supports subagent dispatch (explicit request required). The approach: create `AGENTS.md`, `.codex/` config directory, and an installation guide that explains skill discovery setup.

### User-Facing Behavior

```gherkin
Feature: OpenAI Codex CLI platform support

  Scenario: Plugin provides AGENTS.md for Codex
    Given the plugin repository contains an AGENTS.md at the root
    When Codex CLI starts in a project using this plugin
    Then AGENTS.md is loaded as project-level instructions

  Scenario: Skills are discoverable by Codex
    Given the plugin is installed
    And .agents/skills/ points to the plugin's skills
    When Codex scans for skills
    Then it discovers all SKILL.md files

  Scenario: Codex configuration is provided
    Given the plugin includes .codex/config.toml
    When Codex reads project configuration
    Then hooks are enabled and defaults are set

  Scenario: Hooks are available in Codex format
    Given the plugin includes .codex/hooks.json
    When Codex loads lifecycle hooks
    Then compatible hooks execute on appropriate events

  Scenario: Subagent workflows require explicit request
    Given the plugin is installed in Codex
    When a multi-agent workflow is triggered
    Then AGENTS.md instructs that subagent dispatch requires explicit user request
    And provides Codex-specific guidance on subagent invocation

  Scenario: Knowledge files are accessible
    Given the plugin is installed in Codex
    When a skill references a knowledge file
    Then the file is readable as standard markdown

  Scenario: AGENTS.md documents capability limitations
    Given AGENTS.md is loaded by Codex
    Then it states which features require Claude Code for full capability

  Scenario: Installation guide exists
    Given a user wants to install for Codex
    When they read CODEX-INSTALL.md
    Then it explains skill symlinks, AGENTS.md placement, and config.toml setup

  Scenario: AGENTS.md fits within Codex size limit
    Given AGENTS.md is loaded by Codex
    Then its size is within the 32 KiB default project_doc_max_bytes limit
```

### Architecture Specification

**Components affected**:
- New file: `plugins/agentic-dev-team/AGENTS.md`
- New directory: `plugins/agentic-dev-team/.codex/`
- New file: `plugins/agentic-dev-team/.codex/config.toml`
- New file: `plugins/agentic-dev-team/.codex/hooks.json`
- New file: `plugins/agentic-dev-team/CODEX-INSTALL.md`

**Reused as-is**: All `skills/*/SKILL.md`, all `knowledge/*.md`, all `prompts/*.md`

**Constraints**:
- Do NOT fork or duplicate skill files
- AGENTS.md is standalone, adapted from CLAUDE.md
- Keep .codex/config.toml minimal
- AGENTS.md within 32 KiB limit
- Clearly document capability limitations

**Dependencies**: None — independent. Can be implemented in parallel.

### Acceptance Criteria

- [ ] `AGENTS.md` exists without Claude Code-specific feature references
- [ ] `AGENTS.md` within 32 KiB
- [ ] `.codex/config.toml` exists with hooks enabled
- [ ] `.codex/hooks.json` defines compatible hooks
- [ ] `CODEX-INSTALL.md` covers skill discovery, AGENTS.md, and config setup
- [ ] Skills discoverable by Codex from standard scan path
- [ ] AGENTS.md documents capability limitations vs Claude Code
- [ ] Existing Claude Code functionality unchanged

---

## Consistency Gate

### Slices A-G (core implementation)
- [x] Intent is unambiguous — two developers would interpret each slice the same way
- [x] Every behavior in each intent has at least one corresponding BDD scenario
- [x] Architecture specification constrains implementation to what the intent requires, without over-engineering
- [x] Terminology consistent across all artifacts ("anti-rationalization" is canonical)
- [x] No contradictions between artifacts within any slice
- [x] No contradictions between slices
- [x] Dependency chain is acyclic (A→F, E→G, E→F implementer ref)
- [x] Merge targets identified (agent-registry.md, CLAUDE.md)
- [x] Both status output formats documented (markdown block + JSON field)
- [x] Negative/edge/error cases covered (ambiguous feedback, malformed fixtures, unrecognized status, install failure, unknown project type)

### Slices H1-H3 (platform support)
- [x] Each slice is independent — no cross-dependencies between H1, H2, H3
- [x] All three reuse existing skills/knowledge without forking
- [x] Degradation strategy consistent: document limitations, suggest Claude Code for full capability
- [x] H1 Windows hooks: negative case (no bash), edge case (WSL fallback), no-regression on Unix
- [x] H2 Gemini: unknown frontmatter handled, hook format mismatch handled
- [x] H3 Codex: size limit addressed, install guide covers discovery setup
- [x] No contradictions with slices A-G
