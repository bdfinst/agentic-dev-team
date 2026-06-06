# Proposed Improvements — from External Reviews

> **Sources:** Two external "awareness" reviews of `bdfinst/agentic-dev-team` (HEAD `6bdf15e`, dev-team v6.4.0), both dated 2026-06-06:
>
> - `~/Downloads/2026-06-06-agentic-dev-team-awareness-analysis copy.md` — a peer multi-agent harness comparing itself to dev-team (the "mirror" review).
> - `~/Downloads/agentic-dev-team-unknown-unknowns.md` — an unknown-unknowns reading addressed to the author.
>
> **Purpose:** Summarize the gaps and critiques, then propose improvements ranked by impact and complexity. Each entry carries enough context to seed a `/specs` prompt.
>
> Neither review is a quality critique of the code; both are maps of blind spots. They agree on the central one: *dev-team's own thesis — "convert every finding to a deterministic gate" and "feedback from production is the only evidence that counts" — is not applied to dev-team itself.*

---

## The two recurring meta-critiques

Almost every specific gap below is an instance of one of these:

1. **The cobbler's children go barefoot.** The plugin tests *client* code in CI (bats, shellcheck, knowledge-index freshness, mutation gate) but does not test the *non-deterministic part of itself* — the review agents — in CI. `/agent-eval` exists and is excellent, but runs only when a human remembers. "A gate that doesn't run in the pipeline is documentation."

2. **A gated lifecycle from the person who argued against gated lifecycles.** `/specs → /plan → /build → /pr` batches *trust* (human approves a plan, then trusts the machine through a whole build) the way phase gates batch *work*. The author's own CD conviction (small batches, integrate continuously, "done means released," shrink blast radius rather than harden the gate) is absent from the workflow he gave his agents. This is a paradigm question, not a bug — but it reframes several improvements below.

Supporting observation both reviews make: **the author batches *around* his own workflow** (bursty commits, `.prompts/` hand-framed prompts that route past the front door, the orphan `agent-ast.md` spec that escaped issue discipline). When the expert's ad-hoc path beats the paved road, the paved road is mispriced — and only telemetry or honest self-tally will reveal where.

---

## Summary matrix

Impact × Complexity. Impact = how much it changes decisions/quality/credibility. Complexity = build effort + conceptual risk.

| #  | Improvement | Impact | Complexity | Theme |
|----|-------------|--------|------------|-------|
| 1  | Agent-eval regression gate in CI | High | Low | Self-testing |
| 2  | Prose/Targets slop cleanup + de-buzzword | Med | Low | Credibility |
| 3  | Eval-corpus-as-semver contract | High | Low–Med | Self-testing |
| 4  | Runtime cost/token metering | High | Med | Observability |
| 5  | Eval variance & saturation data collection | Med | Med | Self-testing |
| 6  | `updatedInput` hook-contract conformance test | Med | Low | Self-testing |
| 7  | Resolve the Multi-LLM/Gemini vestigiality | Med | Low–High | Scope honesty |
| 8  | Opt-in privacy-clean telemetry beacon | High | Med | Observability |
| 9  | Knowledge ablation testing (demand-side) | Med | Med | Self-testing |
| 10 | Mutation testing for prose/prompts | High | Med–High | Self-testing (novel) |
| 11 | Concurrency / multiplayer collision model | High | Med–High | Correctness |
| 12 | Persona-vs-context-boundary empirical test | High | Med | Architecture |
| 13 | Process/workflow eval (A/B the ceremony) | High | High | Self-testing (novel) |
| 14 | Per-increment trunk integration topology | Paradigm | High | CD alignment |
| 15 | Automatic post-session learning loop | Med | Med–High | Learning |
| 16 | Component extraction / publication | Med | Low | Distribution |
| 17 | Reconcile `agent-ast.md` orphan spec | Low | Low | Hygiene |

Suggested sequencing: **1 → 2 → 6 → 3** are cheap, high-leverage, and unblock the rest. **4 → 8** build the observability spine that **5, 13, and the moonshots** depend on. **10, 12, 13, 14** are the novel/paradigm bets — sequence them after the spine exists.

---

## Detailed entries

Each entry: the gap, why it matters, complexity notes, and a **Spec prompt seed** (paste into `/specs`).

---

### 1. Agent-eval regression gate in CI — *High impact, Low complexity*

**Gap.** bats, shellcheck, and the knowledge-index freshness gate all run in CI. `/agent-eval` — the only thing that verifies the 20 review agents actually detect what they claim — runs when the author remembers. A commit can regress an agent's accuracy against the existing fixture corpus and merge green. By dev-team's own standard, the agents are the untested part of the system, and they're the *non-deterministic* part that needs the pipeline most.

**Why it matters.** This is the single most-emphasized gap across both reviews ("the most Finster-shaped gap in the repo"). It directly contradicts the repo's doctrine. Even a 1-trial smoke run beats zero.

**Complexity.** Low — the eval runner, fixtures, and grading already exist. Work is a GitHub Actions job + a path filter + a pass/fail threshold + handling non-determinism (smoke vs. full, retry/quorum policy).

**Spec prompt seed:**
> Add a CI gate that runs `/agent-eval` (or its underlying runner) on every PR that touches `plugins/dev-team/agents/`, `plugins/dev-team/skills/`, or `plugins/dev-team/knowledge/`. Define a deterministic pass/fail contract given non-deterministic agents: choose between a 1-trial smoke run vs. multi-trial quorum, set per-agent regression thresholds (e.g., recall must not drop below baseline, no new false positives above the ≤10% policy), decide how flaky fixtures are quarantined vs. blocking, and where the baseline lives. Specify runtime/cost budget for the job and how it degrades when the model API is unavailable. Acceptance: a PR that regresses any fixture's expected status/severity/mustMention fails CI with a readable diff.

---

### 2. Prose / Targets slop cleanup + de-buzzword — *Med impact, Low complexity*

**Gap.** Prose that no sensor touches has drifted into fiction. Cited: "User-level configuration updates through **federated learning**" (`plugins/dev-team/CLAUDE.md:29` — it's a config file), "**LSTM-inspired gates**" for context summarization (line ~175 — borrowed buzzword), and a Targets section claiming "< 5% hallucination rate" and "10–15% overall efficiency gains" (lines ~220–226) with no instrument anywhere that could measure either. The reviewer's law: *prose a deterministic gate touches stays clean; prose no sensor reaches rots.*

**Why it matters.** Credibility. The repo's whole pitch is rigor; unfalsifiable claims in the flagship CLAUDE.md undercut it and invite exactly the critique these reviews deliver.

**Complexity.** Low — editing. The discipline is the hard part: either delete the claim, soften it to honest language, or commit to building the instrument that measures it (links to #4/#8).

**Spec prompt seed:**
> Audit `plugins/dev-team/CLAUDE.md` (and sibling docs) for claims that no sensor or instrument can falsify. For each: (a) replace metaphor/buzzword borrowing ("federated learning," "LSTM-inspired gates") with literal descriptions of the mechanism; (b) for quantitative Targets (hallucination rate, efficiency gains), either remove them, reframe as aspirational-and-explicitly-unmeasured, or file a follow-up to instrument them. Establish a lightweight rule: any quantitative claim in shipped prose must name the instrument that measures it. Acceptance: no metaphor-as-mechanism language remains; every retained number cites its measurement source.

---

### 3. Eval-corpus-as-semver contract — *High impact, Low–Med complexity*

**Gap.** release-please gives prompts semantic versions, but nobody has defined *what a breaking change is for a prompt.* For an agent, the observable surface is behavior under inputs — which is exactly what `evals/expected/*.json` pins down. The unassembled idea sitting in the repo: **the eval corpus IS the semver contract.** Change keeps all `expected/*.json` green → patch. Change adds expectations → minor. Change requires editing existing expectations → behavioral break → major.

**Why it matters.** Gives Hyrum's law something to grip on (195 stars, 23 forks — users depend on observable behavior). Nobody in agent-tooling has formalized this; first-mover framing.

**Complexity.** Low–Med. Conceptually clean; the work is a classifier that diffs eval results/expectations across a change and asserts the conventional-commit type matches the detected change class, wired into the release-please flow.

**Spec prompt seed:**
> Formalize "breaking change for a prompt" using the eval corpus as the contract. Build a check that, for a given diff to agents/skills/knowledge, classifies the behavioral change: GREEN-preserving (patch), expectation-additive (minor), or expectation-editing (major). Wire it to validate that the PR's conventional-commit type (feat/fix/feat!) matches the detected class, and reconcile with release-please. Define how to treat new agents, deleted fixtures, and threshold-only edits. Acceptance: a PR that edits an existing `expected/*.json` value without a major-bump commit type is flagged.

---

### 4. Runtime cost/token metering — *High impact, Med complexity*

**Gap.** `scripts/measure-tokens.sh` counts the *static* size of files. Nothing measures what `/code-review` actually *spends* per invocation, per agent, per iteration of the 5-loop fix cycle. The budget table in CLAUDE.md is a bill of materials, not a meter. Related: no account-level pace/quota reasoning ("which model should I burn this week").

**Why it matters.** "Agent quality without a cost number is half a vibe." Enables budget enforcement, regression detection on cost, and informs #13 (is the ceremony worth its spend?).

**Complexity.** Med — needs a place to capture per-dispatch token/cost (hook on Agent calls, or post-run parse), an append-only log (the `metrics/config-changelog.jsonl` pattern already exists), and reporting.

**Spec prompt seed:**
> Add runtime cost/token metering for dispatched work. Capture per-invocation, per-agent, and per-fix-loop-iteration token spend for `/code-review` and the orchestration phases, writing to an append-only metrics log (follow the `metrics/config-changelog.jsonl` convention). Provide a report command summarizing spend by agent/command and flagging regressions vs. a rolling baseline. Optionally add account-level pace guidance. Decide capture mechanism (PreToolUse/PostToolUse hook on the Agent matcher vs. transcript parse) and privacy boundaries. Acceptance: after a `/code-review` run, a command prints actual tokens spent per agent and total, and a CI/regression hook can compare against baseline.

---

### 5. Eval variance & saturation data collection — *Med impact, Med complexity*

**Gap.** `/agent-eval` reportedly has pass@k and saturation detection built in, but the data was never collected over time. Which agents are stable? Which fixtures flap? Unknown. "Agent quality without a variance number is a vibe."

**Why it matters.** Variance data tells you which agents/fixtures to trust in the #1 CI gate, and which fixtures to quarantine. Prereq for credible thresholds.

**Complexity.** Med — multi-trial runs are cheap to invoke but need persistent storage, trend reporting, and a flap-detection rule.

**Spec prompt seed:**
> Collect and persist `/agent-eval` variance data over time. Run multi-trial (pass@k) evals, store per-agent/per-fixture pass rates in an append-only log, and report stability trends. Define a "flaky fixture" threshold and a quarantine mechanism so flaky fixtures inform (but don't falsely block) the CI gate in improvement #1. Acceptance: a report shows each agent's pass@k and each fixture's flap rate; flaky fixtures are auto-flagged.

---

### 6. `updatedInput` hook-contract conformance test — *Med impact, Low complexity*

**Gap.** `agent-model-resolve.sh` is a *rewriting* hook (PreToolUse returns `updatedInput` with the resolved model snapshot). ADR-0004:108 admits the `updatedInput` behavior it relies on is undocumented harness behavior. A harness change could silently break model routing with no test catching it.

**Why it matters.** A load-bearing, undocumented dependency with no sensor — exactly the failure class dev-team is built to prevent. Cheap insurance for a critical path.

**Complexity.** Low — a focused bats/integration test asserting that a dispatch with a tier alias emerges with the resolved snapshot, and that unresolvable states deny.

**Spec prompt seed:**
> Add a conformance test for the `updatedInput` PreToolUse rewrite contract that `agent-model-resolve.sh` depends on (per ADR-0004). Assert: a dispatch carrying a tier alias is rewritten to the resolved snapshot; 3-hop alias chains and cycle detection behave as specified; unresolvable states deny; bump events log to JSONL. The test must fail loudly if the harness's `updatedInput` semantics change. Acceptance: a deliberately broken resolution table or a simulated contract change turns the test red.

---

### 7. Resolve the Multi-LLM / Gemini vestigiality — *Med impact, Low–High complexity*

**Gap.** A "Multi-LLM Routing" table mentioning Gemini exists in `plugins/dev-team/CLAUDE.md:163-168`, but nothing implements it — zero Gemini references in any `.sh`/`.py`/`.json`. The whole stack is Claude-Code-locked (hooks, marketplace, Agent matchers). A vestigial organ: prose promising a capability the mechanism doesn't deliver.

**Why it matters.** Scope honesty (ties to #2). Either the doc lies, or there's a real roadmap item. The agent-agnostic-baseline / Agent Skills open-standard direction is outside the current mental model — worth a deliberate decision, not an accidental stub.

**Complexity.** Low if the resolution is "delete the table / mark explicitly aspirational." High if the resolution is "actually implement multi-LLM routing."

**Spec prompt seed:**
> Decide and document the Multi-LLM routing posture. Either (a) remove the unimplemented Gemini/Multi-LLM table from `plugins/dev-team/CLAUDE.md` and any vestigial references, or (b) write an ADR committing to agent-agnostic support (which CLIs, what the routing abstraction is, how hooks/matchers generalize beyond Claude Code) and file tracking issues. Pick (a) for now unless there's roadmap intent. Acceptance: no shipped prose promises a routing capability that no code provides.

---

### 8. Opt-in privacy-clean telemetry beacon — *High impact, Med complexity*

**Gap.** The plugin enforces observability on its *targets* and has none of its own. Unknown, empirically: which hooks fire in users' repos and how often; the `--no-verify` bypass rate of the pre-commit review gate (an advertised bypass makes the gate advisory and invisible); whether anyone runs `/specs` or skips to `/build`; which of the 38 skills have never been invoked by anyone. "No production feedback loop, in a system whose author's core thesis is that production feedback is the only evidence that counts."

**Why it matters.** Converts the roadmap from introspection to evidence. Reveals where users (and the author himself) route around the paved road. Foundation for the canary moonshot.

**Complexity.** Med — the data model is trivial (event name + verdict, no payloads), but opt-in consent UX, privacy guarantees, transport/storage, and the append-only-log convention (already established) need care.

**Spec prompt seed:**
> Design an opt-in, privacy-clean telemetry beacon for the plugin. Emit minimal events (hook/command/skill name + verdict/outcome, plugin version; no code, paths, or payloads). Capture at least: gate firings, `--no-verify` / bypass occurrences, command usage (`/specs` vs. direct `/build`), and per-skill invocation counts. Specify consent flow (default off, explicit enable), what is and isn't collected, transport/storage, and a local-only mode. Reuse the append-only event-log convention from `metrics/config-changelog.jsonl`. Acceptance: with telemetry enabled, a report shows command/skill usage and gate-bypass rates; with it disabled, nothing leaves the machine.

---

### 9. Knowledge ablation testing (demand-side) — *Med impact, Med complexity*

**Gap.** The knowledge corpus has perfect supply-side plumbing (index, four freshness gates, anchor-citation test AC19) but nothing measures the *demand* side: do agents actually consult cited anchors at runtime? Does an agent *with* `knowledge/test-smells.md#assertion-roulette` outperform the same agent *without* it on the fixtures? Which knowledge files have never influenced a verdict? "A library with a perfect catalog and no circulation desk." The xUnit build-out (#73–#77) added five files on what evidence of retrieval value?

**Why it matters.** Tells you which knowledge earns its token cost and which is dead weight — directly informs progressive-disclosure budgets. Novel: nobody does knowledge ablation in this space.

**Complexity.** Med — run the eval corpus with a knowledge file ablated, diff the grades. The eval harness exists; the work is the ablation harness + reporting.

**Spec prompt seed:**
> Build knowledge ablation testing. For each knowledge file (or anchor), run the eval corpus with that knowledge available vs. ablated and diff agent grades, producing a per-file "retrieval value" score. Flag knowledge files that never change a verdict as candidates for removal or consolidation. Decide ablation granularity (file vs. anchor) and cost budget. Acceptance: a report ranks knowledge files by measured impact on fixture outcomes; zero-impact files are listed.

---

### 10. Mutation testing for prose / prompts — *High impact, Med–High complexity (novel)*

**Gap.** dev-team mutation-tests its JSON schemas (break a fixture → validation MUST fail) but never aimed the same gun at its prompts. The protocol: delete one rule from a skill/agent file → rerun its eval fixtures → if no eval fails, **that rule has no sensor** — it's either dead weight or an untested load-bearing wall. Run over the whole harness, this yields a *coverage map of governance prose.*

**Why it matters.** Both reviews flag this as the standout moonshot — "first mover gets a conference talk and a genuinely new practice." It joins two halves dev-team already owns (eval fixtures + mutation discipline). It also makes #2's "prose with no sensor rots" law mechanically detectable.

**Complexity.** Med–High — needs a rule-extraction/ablation strategy for natural-language rules (harder than fixture mutation), eval reruns per mutation (cost), and a coverage report. Start scoped to one agent.

**Spec prompt seed:**
> Build prose mutation testing for review agents/skills. For a target agent, systematically ablate individual rules/lines from its prompt and knowledge anchors, rerun that agent's eval fixtures per ablation, and record which ablations cause no fixture to fail ("uncovered prose" — dead weight or untested load-bearing rule). Produce a governance-prose coverage map. Define rule-extraction granularity, the cost budget (ablations × trials), and how to distinguish dead weight from missing-fixture. Start with a single agent (e.g., the one whose identity is recall) as a proof of concept. Acceptance: for the pilot agent, a report lists each rule as covered (an eval depends on it) or uncovered.

---

### 11. Concurrency / multiplayer collision model — *High impact, Med–High complexity*

**Gap.** The pitch is a *team* (`/issues-from-plan` distributes work; README addresses organizations), but every coordination primitive is local single-writer state: `memory/*-progress-*.md`, the `.review-passed` gate file, `.claude/model-overrides.json`. Two humans running `/build` on adjacent features in the same repo: whose progress files win? Whose `.review-passed` does the pre-commit hook honor (it's hash-bound to a staged set — does that save it)? The multiplayer hypothesis is untested; the repo has exactly one external code contribution.

**Why it matters.** "Designed for teams" is currently a claim, not a finding. Processes validated on one expert collapse in characteristic ways at N=2, and the failures are never where the designer guesses.

**Complexity.** Med–High — first an afternoon of adversarial pairing to *find* the collisions (cheap), then a design for concurrency-safe local state (namespacing by branch/worktree/user, conflict detection).

**Spec prompt seed:**
> Investigate and harden multiplayer/concurrent use. Phase 1: adversarially reproduce collisions with two agents/users operating in the same repo at once — progress files (`memory/*-progress-*.md`), the `.review-passed` gate (verify whether its staged-set hash binding already protects it), and `model-overrides.json`. Document each failure mode. Phase 2: design concurrency-safe coordination (namespacing by branch/worktree/user, conflict detection, or worktree-isolation guidance) and decide whether the plugin enforces or merely documents safe concurrent use. Acceptance: a reproduction of each collision exists, and either a fix or an explicit documented constraint resolves it.

---

### 12. Persona-vs-context-boundary empirical test — *High impact, Med complexity*

**Gap.** The repo's sharpest sentence — "The primary value of sub-agents is **context isolation**, not persona specialization" (`plugins/dev-team/CLAUDE.md:134`) — refutes its own public face: 11 personas mirroring a 2015 enterprise org chart (Product Manager, Architect, QA, Tech Writer, UI/UX…). The author pays real maintenance (registries, token budgets, model tiers, audit rules *per persona*) for a value his architecture note locates elsewhere (context boundaries: by data contract, by verification family, by blast radius). Some components already follow that logic (`codebase-recon` is a context boundary, not a persona). **The eval harness can answer this empirically: same fixtures/skills/anchors, persona frontmatter on vs. off, multi-trial pass@k.**

**Why it matters.** Tests the deepest structural assumption in the repo with the instrument already built. May justify dissolving org-chart skeuomorphism into context boundaries — less maintenance, clearer architecture — or may validate personas with data. Either outcome is a strong story.

**Complexity.** Med — the experiment is cheap (toggle frontmatter, rerun evals). The hard part is acting on a result that says "the costume isn't earning its keep."

**Spec prompt seed:**
> Empirically test whether persona specialization adds detection value beyond context isolation. Using the existing eval harness, run the review agents with persona frontmatter/identity prose ON vs. OFF (same skills, knowledge anchors, fixtures), multi-trial, and compare pass@k. Extend the question to team agents where feasible. If personas don't measurably improve outcomes, propose a migration toward context-boundary decomposition (by data contract / verification family / blast radius) and quantify the maintenance reduction. Acceptance: a report shows the persona-on vs. persona-off delta per agent, with a recommendation grounded in the numbers.

---

### 13. Process / workflow eval — A/B the ceremony — *High impact, High complexity (novel)*

**Gap.** dev-team evals its *agents* hard but never evals its *workflow*. Is three-phase + 4 plan critics + 20 reviewers + 5-loop fix better than a direct pass? No fixture, no A/B, no recall measurement on the process itself. "The machine is measured; the assembly line is faith." Nobody publishing in this space has process-level ground truth.

**Why it matters.** The first harness with process-level recall numbers "stops arguing philosophy and starts quoting evidence." Directly tests whether the ceremony (and the trust-batching of #14) earns its cost. Depends on #4 (cost meter) to make the comparison fair.

**Complexity.** High — needs seeded tasks with known-correct outcomes, two pipelines (full vs. direct), and metrics (defect escape, tokens, wall-clock). Designing unbiased ground-truth tasks is the hard part.

**Spec prompt seed:**
> Build a process-level eval. Seed N tasks with known-correct outcomes (intended behavior + known defects to catch). Run each through (a) the full `/specs → /plan → /build → /pr` workflow with critics and the fix loop, and (b) a direct implementation pass. Measure defect escape rate, tokens spent (using improvement #4's meter), and wall-clock. Report where the ceremony pays for itself and where it doesn't, broken down by task complexity (the README already says skip `/specs` for simple tasks — quantify that boundary). Acceptance: a report quantifies the full-workflow vs. direct-pass tradeoff on at least defect-escape and cost.

---

### 14. Per-increment trunk integration topology — *Paradigm impact, High complexity*

**Gap.** The workflow batches *trust*: the human approves one plan, then trusts the machine through an entire build, integrating at the end. This is a stage-gated lifecycle authored by the person whose career argues stage gates batch risk rather than reduce it. `/plan` requires each step to leave the codebase *committable* — but never *releasable*. "Done means released" is absent. The dissolution path, in the author's own vocabulary: **stop hardening the gate; shrink the blast radius.** Let each plan step integrate to trunk dark (behind a flag); let review agents run as post-merge monitors with auto-revert authority instead of pre-merge gates with fix loops; let the human approve *exposures* (flag flips), not *plans*. Trust batch size drops from "one feature" to "one increment," and "is this agent's code safe to merge?" stops needing an answer because merging stopped being the dangerous moment.

**Why it matters.** This is the deepest reframe in both reviews. It aligns the harness with the author's own CD thesis and is genuinely unbuilt — "you're one of perhaps five people alive with both the CD conviction and the agent harness to do it." The third reviewable artifact (running software per increment) is more trustworthy than either 200 lines of plan or 2,000 lines of code.

**Complexity.** High and partly conceptual — depends on flag infrastructure, per-increment integration discipline, post-merge monitoring with revert authority, and a rethink of where the human gate sits. Best pursued *after* #13 produces evidence and #8 provides telemetry.

**Spec prompt seed:**
> Explore a continuous-integration topology for agent work (write as an ADR/spike first, not an implementation). Define the smallest deployable increment of *trust* for an agent and argue why it should be "one green TDD step / one flagged increment" rather than "one approved plan." Specify: each `/build` step integrates to trunk behind a flag; review agents optionally run as post-merge monitors with auto-revert authority rather than only as pre-merge gates; the human approval moves from approving plans to approving exposures (flag flips). Identify what flag/rollback/observability infrastructure the plugin would assume or provide, and what stays gate-based. Acceptance: an ADR that states the trust-batch-size thesis, the topology, the required infrastructure, and a migration path from today's phase gates — with explicit non-goals.

---

### 15. Automatic post-session learning loop — *Med impact, Med–High complexity*

**Gap.** The feedback loop is entirely keyword-driven (`amend`, `learn`, `remember`, `forget` → audited config writes). Disciplined, but manual: no post-session mining, no transcript analysis, no findings bus, no consolidation. "The system learns only when its operator remembers to teach it." (Contrasted with the peer harness's automatic session-analysis → findings → consolidation → drip.)

**Why it matters.** Manual learning under-fires exactly when the operator is busy. Automatic mining surfaces recurring corrections the operator forgot to formalize. Pairs naturally with #8 telemetry.

**Complexity.** Med–High — transcript/session mining, candidate-finding extraction, and a human-in-the-loop consolidation step (must preserve the existing audited-write governance, not bypass it).

**Spec prompt seed:**
> Add an optional automatic learning loop that complements the manual `learn`/`amend`/`remember` flow. After a session, mine the transcript for recurring corrections, repeated manual fixes, and gate bypasses; surface them as *candidate* learnings for human approval (never auto-write — preserve the existing audited-config governance with `previous_value`/`new_value`/`approved_by`). Define what signals count, dedup/consolidation, and the surfacing UX. Acceptance: after a session containing a repeated correction, the system proposes a learning the operator can accept or reject, recorded in the config changelog.

---

### 16. Component extraction / publication — *Med impact, Low complexity*

**Gap.** Three components are "bigger than the repo" and buried where nobody will find them: (a) the **zero-kill mutation gate** (a PostToolUse hook detecting RED→GREEN that blocks tests killing no mutants), (b) **schema mutation testing** for inter-agent contracts (corrupt the fixture, assert validation fails), and (c) the **rules-vs-prompts policy** with a measured ≤10% FP threshold deciding rule vs. judgment — "a general theory of deterministic/probabilistic division of labor disguised as a YAML housekeeping doc." Each could be a standalone repo, a talk, or a 5-Minute-DevOps piece.

**Why it matters.** Distribution is being decided by not deciding. These are the differentiators competitors can't copy by prompt-theft (the measured ones especially). Low effort, high reputational return.

**Complexity.** Low — mostly writing/extraction, not engineering.

**Spec prompt seed:**
> Plan the extraction/publication of three under-distributed components: the zero-kill mutation gate, schema mutation testing for inter-agent contracts, and the rules-vs-prompts FP-threshold policy. For each, decide the vehicle (standalone repo, blog/5-Minute-DevOps piece, conference talk, or docs spotlight), the minimal extraction needed to stand alone, and the headline claim. Acceptance: a short publication plan per component with vehicle, audience, and the one-sentence novel claim.

---

### 17. Reconcile the `agent-ast.md` orphan spec — *Low impact, Low complexity*

**Gap.** `agent-ast.md` sits at the repo root — a full spec for a "Universal AST Harvester" (cross-repo structural indexes, DDD-classified API manifests, incremental by commit SHA) that was never built and never became an issue, in a repo with otherwise exemplary issue discipline. "When an idea is big enough, it escapes your own system. What else has?" One review notes it's effectively a moldable-development / deterministic-structure-extraction backend.

**Why it matters.** Hygiene and integrity of the issue-discipline claim. Either the idea is alive (make it an epic/issue) or it's dead (archive it). A spec floating at root contradicts the governance the repo otherwise models.

**Complexity.** Low.

**Spec prompt seed:**
> Reconcile the orphan `agent-ast.md` spec with the repo's issue discipline. Decide: promote it to a tracked epic/issue with slices, relocate it to `docs/spikes/` as an explicit not-yet-scheduled spike, or archive/delete it. If kept, state the deterministic-structure-extraction value proposition and how it would feed LLM-optimized views. Acceptance: no orphan spec remains at repo root; the idea is either tracked or explicitly shelved with rationale.

---

## What the reviews say dev-team already gets right (don't regress these)

Worth recording so improvements don't undo strengths:

- **Pre-dispatch model resolution** (ADR-0004) — mechanically unbypassable routing.
- **The 550× index rewrite** (ADR-0005) — documented with numbers, four freshness gates.
- **The mutation gate** and **schema mutation tests** — teeth on the contracts.
- **The rules-vs-prompts ≤10% FP policy** — quantitative rule/judgment boundary *with a demotion clause* (a noisy rule gets demoted to prompt surface — an eviction criterion most harnesses lack).
- **`.review-passed` hash-bound to the staged set** — review freshness as content-addressed state, not vibes.
- **`ACCEPTED-RISKS.md`** — governed suppression with expiry dates and mandatory rationale.
- **`freeze` mode** — shipped scope-locking that peers have only TODO'd.
- **`/agent-add` scaffolds eval fixtures** — an agent isn't born without its report card.
- **The agent-readiness scorecard** — a tiered, client-facing "how well can an agent work this repo" rubric (a latent product/consulting angle).

The throughline: the parts touched by a deterministic gate are excellent. Every improvement above is, at bottom, *extend that same discipline to the parts no gate currently reaches — especially the agents, the workflow, and the claims.*
