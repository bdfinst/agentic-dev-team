# Spec: Python Agent Harness Pattern

<!-- spec-version: dev-team/specs@1 -->

**Closes:** #413, #414, #415, #416, #417, #418

## Intent Description

Six dev-team plugin agents — orchestrator, progress-guardian, test-modernization-review, claude-setup-review, token-efficiency-review, and codebase-recon — enforce structural invariants today as LLM prose instructions. Parse plan checkboxes, validate YAML frontmatter, cross-reference JSON artifacts, run git queries, count lines — all currently expressed as things the LLM is asked to do. Because enforcement is embedded in prompts rather than code, it is probabilistic: the LLM can misread a field, round up a violation, or accept a partially-satisfied invariant as "close enough."

This initiative extracts all deterministic behavior from these six agents into Python scripts under `scripts/`, establishing a consistent hybrid harness pattern across the plugin: Python enforces structural invariants; LLM calls are reserved for the residual that genuinely requires judgment (scope-creep verdict, Gherkin quality assessment, architectural synthesis, rule coherence). Calling surfaces — skills and hooks — are updated to invoke the Python scripts directly rather than dispatching the markdown agents. The six markdown agent files are retained and updated to describe the Python implementation they specify, rather than acting as executable definitions themselves.

## Architecture Specification

### New scripts

| Script | Agent replaced | Deterministic checks | LLM residual |
|---|---|---|---|
| `scripts/orchestrator.py` | `agents/orchestrator.md` | Phase state machine, wave scheduling, persona dispatch (asyncio.gather), barrier/reconcile | Task classification, research, plan decomposition, slice implementation (dispatched to software-engineer) |
| `scripts/progress_guardian.py` | `agents/progress-guardian.md` | Checkbox parse, git-log cross-reference, git-status uncommitted check, branch-diff scope comparison | Scope-creep verdict on out-of-plan files |
| `scripts/test_modernization_review.py` | `agents/test-modernization-review.md` | Phase artifact structure, gherkin-bindings.json ↔ .feature cross-reference, disabled-tests.json schema, coverage numeric comparison | Gherkin quality (phase 2), assessment completeness (phase 1) |
| `scripts/claude_setup_review.py` | `agents/claude-setup-review.md` | Frontmatter field presence/type, effort value, unsupported field blocklist, path resolution, kebab-case naming, duplicate name detection | Rule coherence, description accuracy, instruction clarity |
| `scripts/token_efficiency_review.py` | `agents/token-efficiency-review.md` | CLAUDE.md char/rule counts, per-file line counts, token counts via `scripts/measure-tokens.sh` | Role preamble, filler/hedging, redundant restatements (prose files only) |
| `scripts/codebase_recon.py` | `agents/codebase-recon.md` | Metadata discovery, language enumeration, git history probe, inventory emit, schema validation, atomic artifact write | Entry point identification, architecture mapping, security surface scan |

### Integration model (Decision 1 — Option A)

Calling skills and hooks invoke Python scripts directly. Markdown agents become prose specs, no longer dispatched at any call site.

| Caller | Script invoked |
|---|---|
| `/build` (step boundary + pre-PR) | `python3 scripts/progress_guardian.py` |
| `/pr` preflight | `python3 scripts/progress_guardian.py --pre-pr` |
| `/agent-audit` | `python3 scripts/claude_setup_review.py`, `python3 scripts/token_efficiency_review.py` |
| `/test-modernize` (phase boundary) | `python3 scripts/test_modernization_review.py --repo <slug> --phase <N>` |
| `/explore`, `/domain-analysis`, security-review pipeline | `python3 scripts/codebase_recon.py` |
| `/ship`, `/specs`, `/plan`, `/build` (orchestration) | `python3 scripts/orchestrator.py` |

### Reused infrastructure

- `scripts/measure-tokens.sh` — token counting for token-efficiency-review.py
- `scripts/recon-inventory.sh` — inventory step for codebase_recon.py
- `scripts/lib/deterministic_recon.py` — already implements codebase-recon steps 1, 2, 6 (metadata, language enumeration, git history); codebase_recon.py wraps it
- `scripts/lib/invoke_claude.sh` — LLM invocation for qualitative checks

### Constraints

- Output schema unchanged for all scripts: `{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}`
- Python 3.8+ (no walrus operator, no structural pattern matching, no `match`/`case`)
- No new external Python dependencies beyond PyYAML (already in `requirements-dev.txt`)
- LLM calls fire only when all structural checks pass and the remaining question is genuinely qualitative
- Metrics logging excluded (Decision 2): efficiency signal captured by existing `/session-review` and `/cost-report`; per-call instrumentation adds complexity without proportionate insight at this stage

### Retained agent files

Each of the six `.md` files is updated to:

- Add a header identifying the implementing script: `> **Implemented by:** scripts/<name>.py`
- Remove language that implies the agent is the executor
- Retain the rationale for LLM/non-LLM decision boundaries as documentation

## Acceptance Criteria

### All six scripts

- [ ] Runs without LLM for all deterministic checks; LLM invoked only for documented qualitative checks, only after structural checks pass
- [ ] CLI: `python3 scripts/<name>.py [flags]` exits 0 (clean), 1 (hard errors), or 2 (warnings only)
- [ ] Output is structured JSON matching the existing issue schema, parseable by calling skills without LLM interpretation
- [ ] Calling skills/hooks updated to invoke the script directly; markdown agents no longer dispatched at any call site
- [ ] Corresponding markdown agent updated to prose-spec role with `> **Implemented by:**` header

### `scripts/orchestrator.py`

- [ ] Task classification → fast-path (trivial) / full-pipeline (standard/complex) branch is Python logic, not LLM instruction
- [ ] Phase state (research → plan → implement) written to and read from `memory/` files; `--resume` flag restarts from last completed phase
- [ ] Plan-review persona dispatch uses `asyncio.gather`; results aggregated before human gate proceeds
- [ ] Wave barrier raises a structured error naming the failing slice, listing succeeded worktrees, and printing a resume command; never silently continues

### `scripts/progress_guardian.py`

- [ ] `--plan <path>` flag: parses `[x]`/`[ ]` checkbox state and reports completed/pending steps
- [ ] Git-log cross-reference: reports specific step names with missing commit evidence as hard errors
- [ ] Uncommitted changes at a step boundary are exit 1, not a warning
- [ ] `--pre-pr` flag: asserts all steps `[x]`, exits 0 only when clean; used by `/pr` preflight
- [ ] Scope-creep check: diffs branch file list against plan's declared files; out-of-scope files trigger exactly one LLM call for verdict

### `scripts/test_modernization_review.py`

- [ ] `--repo <slug> --phase <N>` flags required
- [ ] Phase 2: set-difference between scenario IDs in `.feature` files and `gherkin-bindings.json` keys; unbound scenarios are exit 1
- [ ] Phase 3: JSON schema check on `disabled-tests.json`; entry missing `reason` or `skip_tag` is exit 1
- [ ] Phase 4: numeric comparison of coverage delta vs phase-3 baseline; regression is exit 1
- [ ] Phase 5: all four quality targets require a `measured_value` field; missing values are exit 1; unmet targets require `next_action`
- [ ] LLM called only for qualitative checks (phase 1 assessment completeness, phase 2 Gherkin quality) and only after structural checks pass

### `scripts/claude_setup_review.py`

- [ ] Missing required frontmatter field: exit 1 with field name and file path in output
- [ ] `effort` value outside `{low, medium, high}`: exit 1
- [ ] Plugin-unsupported fields (`model`, top-level `tools`): warning (exit 2)
- [ ] Unresolvable path reference: exit 1 with referencing file and line number
- [ ] Non-kebab-case filename or name/filename stem mismatch: exit 1
- [ ] Duplicate `name` fields across agent files: exit 1 listing all conflicting files
- [ ] LLM quality call (rule coherence, description accuracy) fires only when structural checks pass; its findings are `warning` severity, never blocking

### `scripts/token_efficiency_review.py`

- [ ] CLAUDE.md over 5,000 characters: exit 1; over 200 rules: exit 1
- [ ] Per-file over 500 lines: warning in output (exit 2 when no hard errors)
- [ ] Token counts collected by shelling out to `scripts/measure-tokens.sh`; results included in JSON output
- [ ] LLM scoped to prose files (`.md` agent/skill/CLAUDE files); source code files excluded from qualitative pass
- [ ] LLM findings are `warning` severity, never `error`

### `scripts/codebase_recon.py`

- [ ] Steps 1, 2, 6 run without LLM by delegating to `scripts/lib/deterministic_recon.py`; step 7 calls `scripts/recon-inventory.sh` via subprocess with exit-code check
- [ ] Steps 3, 4, 5 are LLM calls with scoped context (relevant candidate files only)
- [ ] Step ordering enforced structurally: each step receives prior step's output as a parameter; no mechanism to skip
- [ ] Output JSON validated against schema v0.2 before write; schema violation raises and partial artifact is not written
- [ ] JSON and Markdown artifacts written atomically (temp file + rename)
- [ ] `recon-inventory.sh` non-zero exit causes the harness to fail with the script's stderr

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Calling-surface integration: scripts called directly (A) vs agents shell out (B) | `requires-stakeholder-input` | Human | Option A chosen. Option B leaves LLM in the path for deterministic checks, burning tokens and latency while only partially solving the reliability problem. Calling-surface updates are a one-time cost; enforcement determinism is permanent. |
| Metrics logging scope: `metrics/` instrumentation for all 6 scripts vs orchestrator only vs none | `requires-stakeholder-input` | Human | Excluded from all scripts. The efficiency improvement is the conversion itself. Per-call instrumentation of the remaining (genuinely necessary) LLM calls adds complexity without proportionate insight. Session-level efficiency signal already captured by `/session-review` and `/cost-report`. |
| LLM invocation mechanism in Python scripts | `inferable` | Inference | `scripts/lib/invoke_claude.sh` already exists for this purpose and is used by other scripts. Python scripts shell out to it via subprocess, consistent with existing patterns. |
| Python version floor | `inferable` | Inference | Existing scripts use `from __future__ import annotations` and other 3.8 idioms. 3.8+ is the floor; no walrus, match/case, or other newer features. |
| `--resume` flag scope (orchestrator only vs all scripts) | `inferable` | Inference | Only orchestrator manages multi-phase state that benefits from resume. Other scripts are stateless validators; re-running them from scratch is the correct behavior. |

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret it the same way
- [x] Every behavior/goal in the intent maps to at least one acceptance criterion
- [x] Architecture constrains without over-engineering — reuses existing infrastructure, no new dependencies
- [x] Terminology consistent across artifacts (`scripts/`, markdown agent, hybrid harness, LLM residual)
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — all five items either resolved by human or documented as inferable with rationale
