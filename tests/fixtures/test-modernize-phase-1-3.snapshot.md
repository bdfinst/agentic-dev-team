### 1. Analyze — `/cd-test-architecture` + `/issues-from-assessment`

1. Invoke `/cd-test-architecture <repo-path> [--ci <ci-path>] [--external-tests <loc>]`. It writes the assessment to `reports/cd-test-architecture-<app>.md`.
2. Invoke `/issues-from-assessment <assessment-path> --parent <url-or-empty> --repo-slug <slug>`. It creates the parent + Phase-1 / Phase-2 / Phase-5 children via the resolved CLI (or local plan files) and writes a per-phase index to `memory/test-modernize/<slug>/phase-1.md`.
3. Run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 1`. Surface any blocker findings to the operator and have them resolved before the gate.

**Human gate** — wait for approval before specifying the public interface.

### 2. Specify public interface — `/gherkin-public` (two-pass)

Phase 2 runs in two passes around the human gate so Stories never bind to un-reviewed scenarios.

**Pass A — author scenarios.**

1. Invoke `/gherkin-public <repo-path> --repo-slug <slug>`. It reads the component map from `memory/test-modernize/<slug>/phase-1.md` and writes `.feature` files per public surface (API endpoint, UI flow, batch-job entry point, library export, event type) to `features/test-modernize/` (or `./specs/test-modernize/` if no `features/` dir exists). It does NOT create Stories on this pass.
2. Run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 2`.

**Human gate** — operator validates the Gherkin scenarios. This is a hard stop. The operator may edit `.feature` files in place before approving.

**Pass B — bind Stories to approved scenarios.**

1. Once approved, invoke `/gherkin-public <repo-path> --repo-slug <slug> --parent <url-or-empty> --create-stories`. This pass creates one `[Component tests] <component> · <surface>` Story per approved public surface via the resolved tracker CLI. Each Story's Acceptance Criteria cites the specific `<feature-file>::<scenario-name>` pairs its tests must satisfy. The scenario → Story-id map is written to `memory/test-modernize/<slug>/gherkin-bindings.json`.
2. Backfill the predecessor placeholders the Phase-1 Stories left for `[Component tests]` (contract / integration / E2E / resilience Stories blocked by the new Story IDs).

### 3. Audit + baseline coverage — `/test-audit-disable` + `/coverage-baseline`

1. Invoke `/test-audit-disable <repo-path> --repo-slug <slug>`. Disables every cannot-fail test (skip + tag, never delete) and records reasons in `memory/test-modernize/<slug>/disabled-tests.json`.
2. Invoke `/coverage-baseline <repo-path> --parent <url-or-empty> --repo-slug <slug> --workflow test-modernize`. Runs the project's coverage tool, records the baseline at `memory/test-modernize/<slug>/baseline-coverage.json`, and posts the number to the parent issue (or `./plans/test-modernize/FEATURE.md` in local-files mode). Passing `--workflow test-modernize` keeps the memory namespace under `memory/test-modernize/` exactly as before.
3. Run `python3 scripts/test_modernization_review.py --repo <repo-slug> --phase 3`.

**Human gate** — baseline accepted before adding tests.

