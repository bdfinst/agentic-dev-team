# Developer notes — extending and maintaining the plugin

This page is for people working **on** the dev-team plugin: adding a tool,
agent, or skill, maintaining the eval corpus, or extending the static-analysis
suite to a new language. If you are *using* the plugin for your own
development work, you want the [skills reference](skills.md) and the
[workflows guide](workflows.md) instead — nothing here changes how the plugin
behaves in your project.

## Where plugin-development knowledge lives

Plugin-development documentation is spread across a few focused files. This
table is the jumping-off point; each doc stays the authority for its own
topic.

| Topic | Doc | What it covers |
|---|---|---|
| Agent architecture | [`agent-architecture.md`](agent-architecture.md) | How agents are structured, routed, and dispatched. |
| Agent authoring | [`agent_info.md`](agent_info.md) | The per-agent file format and required sections. |
| Eval architecture | [`eval-system.md`](eval-system.md) | How the agent-eval system is built and gated. |
| Running evals | [`eval-running-guide.md`](eval-running-guide.md) | The operational procedure for eval runs and variance batches. |
| Eval upkeep | [`eval-maintenance.md`](eval-maintenance.md) | Grading rules, the calibration trap, and corpus discipline. |
| Adapter & ruleset lifecycle | [`static-analysis-integration/maintenance.md`](../skills/static-analysis-integration/maintenance.md) | Ownership, drift detection, and deprecation for shipped adapters and rulesets. |
| Adding agents, skills, or hooks | [root `CLAUDE.md`](../../../CLAUDE.md) § "Adding agents, skills, or hooks" | Where each artifact type lives and the structural audit to run afterwards. |
| Script conventions | [ADR 0014](../../../docs/adr/0014-python-for-cross-os-scripts.md), [ADR 0015](../../../docs/adr/0015-bash-removal-complete.md) | Why every shipped script is Python 3.8+ stdlib-only, and the completed bash removal. |

The rest of this page covers the one extension path that touches several of
these files at once and has no other single writeup: adding a new language to
the static-analysis suite.

## Playbook: adding a static-analysis language

The static-analysis suite has two consumption sites that share one registry:

- **`/code-review`'s full-repo pre-pass** — the
  [static-analysis-integration skill](../skills/static-analysis-integration/SKILL.md)
  runs every detected tool over the target set, normalizes output to the
  unified finding envelope, deduplicates, and hands confirmed findings to the
  review agents.
- **`/build`'s static self-heal pass** — at each review checkpoint, language
  **lanes** fix or surface mechanical findings in the changed files before
  semantic review. The mechanism (scoping, the shared fix loop, the 2-attempt
  cap, detection and provider binding, the degradation ladder) is specified
  once in [`static-self-heal.md`](../skills/build/references/static-self-heal.md);
  lanes are registered in
  [`tool-configs.md` § Build-time lanes](../skills/static-analysis-integration/references/tool-configs.md#build-time-lanes).

Adding a language means wiring both sites plus the user-facing setup docs.
The four landed lanes are the worked examples this playbook generalizes from:

| Lane | Issue | Autofix slot | Diagnostic slot | Notable shape |
|---|---|---|---|---|
| Python | #807 | ruff (SARIF-native) → black + flake8 | mypy (Tier 3 JSON adapter) → pyright (gated) | Two independent slots, each with a recognized-equivalent fallback. |
| JS/TS | #808 | oxlint → biome → eslint (demoted) | none — verify via autofix check mode | A slow-but-qualified provider bound with granularity demotion. |
| C# | #809 | `dotnet format` (SDK-builtin) | Roslyn ErrorLog SARIF from the GREEN-confirming build | Diagnostics ride a build the pipeline already pays for. |
| Java | #810 | none — no fast Java autofixer exists | PMD (SARIF-native) → checkstyle | Diagnostic-only lane; standalone installer (the exception). |

**Audience boundary.** This playbook is for plugin maintainers wiring a new
language *into the plugin*. The
[per-language setup guide](../skills/static-analysis-integration/references/language-setup.md)
is for end users configuring their own repo's toolchain, and it remains the
single source of truth for install/config/verification commands. The two
cross-link and never duplicate: your job here includes *adding* that guide's
new section, not restating its content anywhere else.

### First, classify the candidate tool — two independent questions

Every candidate tool gets sorted by two axes, and they are genuinely
independent — knowing one tells you nothing about the other:

1. **Output format: SARIF-native, or needs an adapter?** This decides the
   tool's tier in `tool-configs.md`. A tool that emits SARIF is consumed raw
   by the [shared SARIF parser](../skills/static-analysis-integration/references/sarif-parser.md)
   (Tier 1/2). A tool with only JSON or line-based output needs a bespoke
   adapter (Tier 3), and the budget is hard: **≤ 40 LOC**. If an adapter
   wants to be bigger than that, the tool is fighting the pipeline —
   reconsider the candidate.
2. **Capability: autofix-capable, or diagnostic-only?** This decides which
   lane **slot** the tool can provide. An autofix tool runs the mechanical
   pre-fix and can double as its own verifier in check mode; a
   diagnostic-only tool feeds findings to the coding agent inside the shared
   fix loop.

The worked examples cover all four quadrants: ruff is SARIF-native *and*
autofix-capable; PMD is SARIF-native but diagnostic-only; mypy needs an
adapter and is diagnostic-only; `dotnet format` is autofix-capable and needs
no output format at all, because verification comes from its own
`--verify-no-changes` mode and from the Roslyn ErrorLog SARIF.

Version-pin early, and re-check the format question against the pinned
version: oxlint was specced as a Tier 3 JSON adapter, but by implementation
time the pinned release had gained native SARIF, so it landed adapter-free.
Upstream SARIF support arriving is the cheapest adapter deletion you will
ever do.

### Wiring the `/code-review` side

A new tool becomes visible to `/code-review` through an entry in
[`tool-configs.md`](../skills/static-analysis-integration/references/tool-configs.md),
under the tier its output format earned. The existing entries define the
house metadata shape; a complete entry carries:

- **Invocation** — the exact command, SARIF-first.
- **Install** — the repo-level form (see the install conventions below).
- **Install hint** — in the skill's fixed format:
  `<tool-name> — <capability-tier>. install: <command>`. This exact string
  is what users see when the tool is missing, so it names the repo-level
  install, never a global one.
- **Detection** — how presence is probed. Repo-local locations come first,
  then PATH: a project-local `node_modules/.bin` binary or a gitignored tool
  directory must be found even when nothing is user-installed.
- **Language-conditional dispatch** — the tool is probed, dispatched, and
  its missing-tool hint surfaced *only when matching files are in the target
  set*. A non-Java repo must never see a "pmd missing" warning. Absence is
  never a pipeline failure.
- **Adapter** — "none" for SARIF-native tools; otherwise the ≤ 40 LOC
  adapter under the skill's `adapters/`, with its field-mapping table in the
  entry. Per the [maintenance policy](../skills/static-analysis-integration/maintenance.md),
  a SARIF adapter comes first — bespoke JSON only when upstream genuinely
  has no SARIF plan.
- **Exit-code semantics** — when the tool distinguishes "findings exist"
  from "tool broke" by exit code (PMD exits 4 on violations), the entry says
  so, because the degradation ladder treats the two very differently.

Two more pieces ride along with the entry:

- **A fixture pair** under `evals/static-analysis-tools/tier1-mocks/<tool>/`
  — a mock tool output plus the expected unified findings. This is the
  regression harness proving the parser (or adapter) reads the tool
  correctly, and the maintenance policy makes it a precondition for adding
  any tool.
- **A dedup-chain decision.** The pre-pass deduplicates findings across
  tools and keeps the higher-priority source; the chain lives in the skill's
  step 4. Most language-specific tools need no new thought — semgrep already
  outranks them all, and the precedent (recorded on the pmd and Roslyn
  entries) is to revisit only if a *second* source for the same language is
  added. A tool that genuinely overlaps an existing one, as oxlint overlaps
  legacy ESLint, gets an explicit ranking.

### Wiring the build-time lane

The self-heal pass never gains per-language logic. Everything a lane does —
how changed files are scoped, how the fix loop retries, when it escalates,
how providers bind — is specified once in
[`static-self-heal.md`](../skills/build/references/static-self-heal.md), and a
new language plugs in as pure registry data: one subsection under
`tool-configs.md` § Build-time lanes. If you find yourself writing loop or
scoping logic for your language, stop — the mechanism doc forbids restating
it, and an accommodation belongs in the mechanism doc (as with C#'s
post-hoc SARIF filtering), not in the lane row.

A lane row declares:

- **Extensions** — the file patterns that route changed files into the lane.
- **Up to two capability slots** — an **autofix** slot and a **diagnostic**
  slot, either of which may be absent. Missing slots are normal, not
  deficiencies: the degradation ladder runs Java diagnostic-only (no fast
  Java autofixer exists), and JS/TS verifies with the autofix tool's own
  check mode rather than carrying a diagnostic slot.
- **An ordered provider list per slot** — the default provider first. The
  default doubles as the **last-resort provider**: the one install hints
  name and `/project-init` installs, chosen only when the probe finds no
  recognized provider already configured. This is the bind-don't-replace
  rule — a project that arrives with black + flake8, or checkstyle, or an
  ESLint config keeps its own tool.
- **A detection probe per provider** — repo-local install locations first,
  then PATH, matching the `/code-review` detection convention.
- **Scoped invocations** — the fix and verify commands as run against the
  checkpoint's changed-file list, plus any wrapper contract the tool needs
  (PMD requires a `--file-list` temp file and must never be invoked with an
  empty set; `dotnet format` treats an empty `--include` as "format
  everything", which is why the mechanism's empty-partition guarantee is
  load-bearing).

Every provider you list must satisfy the mechanism's **provider
qualification contract**: scoped invocation, machine-readable output within
the adapter budget, checkpoint-compatible latency, deterministic exit codes.
A tool that fails the latency item can still bind with its lane demoted to
slice-boundary granularity — that is how a project's existing ESLint config
is honored without slowing the per-step loop. Keep provider lists short and
explicit: every recognized provider is an adapter and a registry row someone
maintains, and this is deliberately not an open-ended plugin system.

### The user-facing setup section and `/project-init`

Two more places make the lane usable by people who did not read any of the
above:

- **A language section in [`language-setup.md`](../skills/static-analysis-integration/references/language-setup.md)**,
  following that guide's "Per-lane section contract": tools and roles,
  repo-level install, configuration, verification, opt-out, and recognized
  equivalent providers, in that order. This is where the actual install and
  verification commands live — the lane row and this playbook link to it
  rather than repeating them.
- **A `/project-init` lane**, so the one-command scaffold performs the same
  repo-level install the setup section documents manually. Each
  `language-setup.md` section carries the one-line pointer to
  `/project-init`; the guide stays the source of truth for the manual
  commands.

### Install conventions

The four landed lanes established conventions that new lanes inherit:

- **Shipped scripts are Python 3.8+ stdlib-only.** No bash, no Git Bash
  requirement; Windows portability comes from the Python stdlib. See
  [ADR 0014](../../../docs/adr/0014-python-for-cross-os-scripts.md) and
  [ADR 0015](../../../docs/adr/0015-bash-removal-complete.md).
- **Repo-level over user-level, always.** The install lands in the project's
  own dependency mechanism so the toolchain is versioned with the repo and
  reproducible for every contributor and CI: an npm devDependency (oxlint),
  a venv / dev-requirements entry (ruff, mypy), a `global.json` SDK pin
  (dotnet), or a repo-local gitignored tool directory (`.pmd/`). Never
  `npm install -g`, `pip install --user`, or a global toolchain assumption.
- **A standalone installer is the exception, not the rule.** Of the four
  lanes, only Java needed one (`scripts/install-java-static-analysis.py`),
  because PMD has no project-level dependency mechanism to ride. Prefer the
  project's own mechanism; write an installer only when none exists.
- **Idempotent re-runs.** Running the install twice must be safe and cheap —
  an existing install is detected and nothing is re-downloaded.
- **Single-source version pinning.** The pinned version lives in exactly one
  place (the lockfile, `global.json`, or one constant in the installer), so
  a bump is a one-line change.

### Retiring an older tool

Bind-don't-replace means older tools do not disappear when a better one
lands: a project configured for ESLint keeps ESLint, and legacy tools stay
in the provider list and dedup chain as long as real projects arrive with
them. Retirement is therefore a deliberate decision, and the precedent to
copy is the oxlint/ESLint checklist ("When a project may drop ESLint
entirely" in [`tool-configs.md`](../skills/static-analysis-integration/references/tool-configs.md))
— a **decidable** test, not a vibe:

1. Every rule the old tool enforces in this project is either covered by the
   new tool's pinned version or explicitly acknowledged as not relied on.
2. No plugin/extension of the old tool contributes an enabled rule the new
   tool lacks (framework ESLint plugins were the real blocker there).
3. A one-time dual run over the repo shows the old tool reporting nothing
   the new tool misses.

Until all three hold, both tools run, with overlap suppressed (the
`eslint-plugin-oxlint` pattern) and the dedup chain ranking the newer tool
higher. The same shape applies to any successor pair — Ruff replacing
pylint/flake8 followed it: the legacy Python entry was retired outright only
once ruff covered the surface, while black + flake8 remain a recognized
*provider pair* for projects that arrive with them. Retiring a tool from the
plugin (deleting its entry and adapter) additionally follows the
[adapter deprecation policy](../skills/static-analysis-integration/maintenance.md):
demote, warn, then remove at the next major contract version — never a
silent deletion.
