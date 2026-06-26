<!-- Extracted from CLAUDE.md ## Skills Registry — do not duplicate here, edit the source -->

# Skills Registry

> This file is extracted from `plugins/dev-team/CLAUDE.md` → Skills Registry. Edit the source table there; this file is a standalone reference copy for agents that need to load only the skills catalog.

User-invocable workflows in `.claude/skills/`. All review skills are executed under orchestrator direction. Model assignment for every agent flows through the **Resolution Procedure** (`agents/orchestrator.md`), enforced by the PreToolUse hook `hooks/agent-model-resolve.sh`.

> **Moved to the `marketplace-dev` plugin.** The plugin-authoring skills `agent-create`, `agent-skill-authoring`, `agent-add`, `agent-remove`, and `add-plugin` are no longer part of dev-team. They — plus a generalized `/plugin-audit` — now live in the companion `marketplace-dev` plugin, which builds and audits Claude Code plugins for any marketplace. Install it from the `bfinster` marketplace.

## Command Table

| Command | File | Role | What It Does |
|---------|------|------|--------------|
| `/agent-audit` | `skills/agent-audit/SKILL.md` | orchestrator | Audit agents/skills/hooks for structural compliance |
| `/agent-eval` | `skills/agent-eval/SKILL.md` | orchestrator | Run eval fixtures, grade accuracy, detect regressions |
| `/agent-readiness` | `skills/agent-readiness/SKILL.md` | worker | Score how agent-ready the current project repo is against the Agent-Readiness Scorecard; emits a tiered JSON/Markdown report (scores your project, not the plugin — use `/harness-audit` for that) |
| `/apply-fixes` | `skills/apply-fixes/SKILL.md` | implementation | Apply correction prompts from `/code-review` output |
| `/benchmark` | `skills/benchmark/SKILL.md` | worker | Capture runtime performance metrics (Core Web Vitals, resource sizes) and compare against baselines |
| `/browse` | `skills/browse/SKILL.md` | worker | Browser-based QA: navigate, screenshot, click, fill forms via Playwright |
| `/build` | `skills/build/SKILL.md` | orchestrator | Execute an approved plan with TDD, inline reviews, and verification evidence; ends with a Farley Score for the branch's tests before prompting for `/pr` |
| `/careful` | `skills/careful/SKILL.md` | worker | Toggle destructive command blocking (rm -rf, force-push, DROP TABLE, etc.) |
| `/code-review` | `skills/code-review/SKILL.md` | orchestrator | Run review agents, auto-fix actionable issues, re-run until clean (up to 5 iterations). Short-circuits documentation-only changesets (skips review; `--force` overrides) |
| `/continue` | `skills/continue/SKILL.md` | orchestrator | Resume work from a prior session using phase progress files |
| `/cost-report` | `skills/cost-report/SKILL.md` | worker | Report actual token spend and dollar cost of dispatched work — per agent and total — and flag cost regressions |
| `/coverage-baseline` | `skills/coverage-baseline/SKILL.md` | worker | Phase-3 of `/test-modernize` — detect the repo's coverage tool, capture line+branch percentages as the post-audit baseline, post to the parent issue or local FEATURE.md |
| `/coverage-delta` | `skills/coverage-delta/SKILL.md` | worker | Phase-4 of `/test-modernize` — re-run coverage and post Δ vs. baseline after each Story closes; when `--story-files` is supplied, also runs scoped mutation testing on those files and emits a structured status (`ok | net_new_survivors | first_measurement | tool_unavailable | skipped_empty_scope`) for the orchestrator to act on; never halts and never overwrites history (atomic temp-file-then-rename writes to`mutation-history.json`) |
| `/explore` | `skills/explore/SKILL.md` | worker | Charter-driven exploratory testing of a running target (Chaos Specialist mode): structured heuristics + adversarial expansion, auto-triages critical defects, writes an incremental report |
| `/freeze` | `skills/freeze/SKILL.md` | worker | Scope-lock editing to a glob pattern; blocks edits outside the pattern |
| `/gherkin-public` | `skills/gherkin-public/SKILL.md` | worker | Phase-2 of `/test-modernize` — author Gherkin scenarios for the entire public interface (API endpoints, UI flows, batch-job entry points, library exports, event types) at the observable boundary |
| `/guard` | `skills/guard/SKILL.md` | worker | Combined `/careful` + `/freeze` for production-critical sessions |
| `/harness-audit` | `skills/harness-audit/SKILL.md` | orchestrator | Analyze harness effectiveness and flag stale components |
| `/help` | `skills/help/SKILL.md` | worker | List all available slash commands with descriptions |
| `/init-dev-team` | `skills/init-dev-team/SKILL.md` | worker | Install plugin prerequisites (jq, python3, mutation tools). Includes a state-aware CodeGraph offer (install / init / silent-confirm based on `command -v codegraph` and `.codegraph/` presence), and bootstraps a JS project via `js-project-init` when JS/TS is selected but `package.json` is absent. |
| `/issues-from-assessment` | `skills/issues-from-assessment/SKILL.md` | worker | Convert a `/cd-test-architecture` assessment into a parent + Phase-tagged child issues via the tracker CLI resolved from the parent URL host (gh / az / glab / acli). Falls back to local plan files when no URL is given or the CLI is missing |
| `/issues-from-plan` | `skills/issues-from-plan/SKILL.md` | orchestrator | Break a plan into independently-grabbable GitHub issues |
| `/js-project-init` | `skills/js-project-init/SKILL.md` | worker | Initialize a new JavaScript project (ES modules, functional style, prettier, eslint, editorconfig, vitest, gitignore) |
| `/model-routing-check` | `skills/model-routing-check/SKILL.md` | worker | Read-only diagnostic for effort-band model routing. Prints the effective band → model map, the ladder (or a ready-to-edit starter), the captured session model, and the most recent routing bumps from the resolver log. |
| `/plan` | `skills/plan/SKILL.md` | orchestrator | Decompose a feature into vertical slices — each with its Gherkin scenarios and TDD steps |
| `/pr` | `skills/pr/SKILL.md` | orchestrator | Run quality gates and create a pull request (enables auto-merge by default) |
| `/quality-targets-converge` | `skills/quality-targets-converge/SKILL.md` | worker | Phase-5 of `/test-modernize` — loop that picks the largest gap to the four quality targets (coverage / mutants / determinism / speed) and dispatches the smallest action to close it |
| `/review` | `skills/review/SKILL.md` | orchestrator | Alias for `/code-review` — same arguments, same behavior |
| `/review-agent` | `skills/review-agent/SKILL.md` | worker | Run a single review agent (used for inline checkpoints) |
| `/review-summary` | `skills/review-summary/SKILL.md` | orchestrator | Generate compact session summary for context continuity |
| `/semantic-scan` | `skills/semantic-scan/SKILL.md` | worker | Build computation register and detect semantic duplicates across architectural layers |
| `/semgrep-analyze` | `skills/semgrep-analyze/SKILL.md` | worker | Run Semgrep SAST and return structured findings |
| `/session-review` | `skills/session-review/SKILL.md` | orchestrator | Mine real session transcripts (via the deterministic `session_extract.py`) and dispatch `session-analysis` to suggest token/rework/accuracy improvements; suggests, never auto-applies |
| `/setup` | `skills/setup/SKILL.md` | orchestrator | Detect tech stack, generate project-level config, hooks, and agent templates |
| `/ship` | `skills/ship/SKILL.md` | orchestrator | Run the full spec→plan→TDD build→code-review→PR(auto-merge) pipeline as one command, pausing at the existing human gates |
| `/telemetry` | `skills/telemetry/SKILL.md` | worker | Manage and report the opt-in, privacy-clean usage telemetry beacon (on/off/status/report) |
| `/test-audit-disable` | `skills/test-audit-disable/SKILL.md` | worker | Phase-3 of `/test-modernize` — detect tests that cannot fail (no assertions, tautologies, self-equality, swallowed exceptions) and disable each by skip-and-tag with the reason; never deletes |
| `/test-design` | `skills/test-design/SKILL.md` | orchestrator | Deep test-design review: dispatch test-review + test-smell-review, score all existing tests (Farley Score), then run test-design-advisor for testability/refactor recommendations (advisory) |
| `/test-health` | `skills/test-health/SKILL.md` | orchestrator | Project-wide test-strategy audit: shape vs. architecture fit, quadrant coverage, flaky/automation maturity, ordered plan. Runs `/test-design` (Farley Score + smell themes) and `mutation-testing` and folds their results in; delegates pipeline assessment to cd-test-architecture (advisory) |
| `/test-modernize` | `skills/test-modernize/SKILL.md` | orchestrator | Modernize a legacy repository's tests for CD as one sequenced workflow — assessment → public-interface Gherkin → audit + baseline coverage → no-refactor adds → minimum refactor + converge on coverage/mutation/determinism/speed targets. Outputs phase issues to ADO, GitHub, GitLab, Jira, or local plans/specs files via the parent issue URL |
| `/triage` | `skills/triage/SKILL.md` | worker | Investigate a bug and write a triage record to `.triage/<slug>.md` with a TDD fix plan |
| `/unfreeze` | `skills/unfreeze/SKILL.md` | worker | Lift the scope lock set by `/freeze` |
| `/upgrade` | `skills/upgrade/SKILL.md` | worker | Check for and apply plugin updates from within a session |
| `/version` | `skills/version/SKILL.md` | worker | Report the installed plugin version |

Referenced from: `plugins/dev-team/CLAUDE.md` → Skills Registry
