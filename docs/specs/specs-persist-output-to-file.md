# Spec: Specs command persists output to file

## Intent Description

The `/specs` command produces four specification artifacts (Intent, BDD scenarios, Architecture notes, Acceptance Criteria) through a collaborative loop with the user. Currently, the results exist only in the conversation — they are lost when the session ends and cannot be referenced by downstream commands (`/plan`, `/build`, spec-compliance-review).

This change makes `/specs` persist its output to `docs/specs/` as a structured markdown file, so that:
- `/plan` can read the spec artifacts when generating implementation steps
- `spec-compliance-review` can diff implementation against the written spec
- Specs survive session boundaries
- The output guardrail ("write to files, not chat") is honored

## User-Facing Behavior

```gherkin
Feature: Specs command persists output to file

  Scenario: Specs output is saved after consistency gate passes
    Given the user runs /specs with a feature description
    And all four artifacts pass the consistency gate
    When the specification is finalized
    Then a markdown file should be created at docs/specs/<slug>.md
    And the file should contain all four artifacts (Intent, BDD scenarios, Architecture notes, Acceptance Criteria)
    And the consistency gate verdict should be included

  Scenario: File name is derived from the feature description
    Given the user runs /specs with "user login with MFA"
    When the specification is finalized
    Then the output file should be named docs/specs/user-login-with-mfa.md

  Scenario: Existing spec file is not overwritten without confirmation
    Given a spec file already exists at docs/specs/user-login-with-mfa.md
    When the user runs /specs for the same feature
    Then the user should be asked whether to overwrite or create a versioned file
```

## Architecture Specification

**Components affected:**
- `plugins/agentic-dev-team/skills/specs.md` — add file output instructions at the end of the workflow

**No new files created in the plugin.** The `docs/specs/` directory is created in the consuming project at runtime.

**Output format:** A single markdown file with H2 sections for each artifact:

```markdown
# Spec: <Feature Name>

## Intent Description
...

## User-Facing Behavior
...

## Architecture Specification
...

## Acceptance Criteria
...

## Consistency Gate
- [x] Intent is unambiguous
- [x] Every behavior has a corresponding BDD scenario
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts
```

**Constraints:**
- File path: `docs/specs/<slugified-feature-name>.md`
- Slugify: lowercase, hyphens for spaces, strip special characters
- The skill already says "no code during specification phase" — file output is an artifact, not implementation

## Acceptance Criteria

1. After the consistency gate passes, a file exists at `docs/specs/<slug>.md` containing all four artifacts
2. The file includes the consistency gate checklist with pass/fail marks
3. If `docs/specs/` does not exist, it is created
4. If a file with the same slug already exists, the user is prompted before overwriting
5. The file path is printed to chat so the user can find it

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior has a corresponding BDD scenario
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts

**Gate: PASS**
