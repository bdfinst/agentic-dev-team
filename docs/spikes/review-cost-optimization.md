# Spike: Economizing the Review Panel

**Status:** analysis — no behavior changed by this document.
**Question:** which reviews are critical on every change, which can become
optional, and which agent work can move into deterministic scripts or
open-source tools?

Method: full inventory of the review-agent roster and its dispatch gates
(`plugins/dev-team/skills/code-review/SKILL.md` step 3,
`plugins/dev-team/scripts/select_lenses.py`), the deterministic tooling that
already exists (`scripts/ci-local.sh`, `plugins/dev-team/hooks/`,
`plugins/dev-team/skills/static-analysis-integration/SKILL.md`), and the
measurement machinery (`plugins/dev-team/skills/harness-audit/SKILL.md`,
`.claude/metrics/review-value.jsonl` per #1624).

---

## 1. Where the cost goes today

A code-touching diff of ordinary size dispatches up to **14 `Scope: always`
lenses** plus any glob/manifest-matched ones. Every agent in the fleet runs
at `effort: high`. By model tier (pricing per
`plugins/dev-team/knowledge/model-pricing.json`: opus $5/$25 per MTok ≈ 1.7×
sonnet ≈ 5× haiku):

| Tier | Always-scoped lenses | Existing gate |
| --- | --- | --- |
| **opus** | correctness-review | change-shape (dropped when no runtime surface); non-executable skip (#1923) |
| **opus** | security-review | none (kept even on the small-diff fast path — by design) |
| **opus** | arch-review | architectural-impact gate (`change_impact.py`) |
| **opus** | domain-review | **none — the only ungated always-on opus lens** |
| sonnet | structure-review, complexity-review, naming-review, test-review, test-smell-review | change-size fast path only (≤3-file diffs) |
| haiku | doc-review, spec-compliance-review, performance-review, concurrency-review, refactor-opportunity-review | performance: change-shape; others: change-size fast path only |

Conditional lenses (already economized): a11y-review and js-fp-review
(glob-scoped), component-architecture-review (added-only, #1733), the three
framework reactivity lenses (manifest-gated), and the three `Scope: on-demand`
repo-wide lenses (token-efficiency, ai-provenance, claude-setup) that moved to
`/repo-review` in #1733/#1735.

A lot of economization machinery already exists and works: the
documentation-only short-circuit, the change-shape gate (#1254), the
change-size fast path (#1339), the architectural-impact gate for arch-review,
verification mode for fix-loop re-dispatches (#1628), deterministic-first
triage in the fix loop (#1610), the static-analysis pre-pass with
don't-re-report dedup, `repo_invariants.py` (#1608), and wave-bounded
dispatch. The opportunities below extend that machinery; none of them invent
a new mechanism category.

---

## 2. Critical vs. optional reviews

### The evidence frame

Two findings from the experiment line anchor this split
(`docs/experiments/RECOMMENDATIONS.md` Rec 5):

- The **structural lenses** (SRP, complexity, coupling, duplication) were the
  one quality axis that separated workflows — they are the *value* lenses,
  but their value shows on multi-file work, not on 3-line diffs.
- Coverage/mutation scores saturate regardless of workflow — thoroughness for
  its own sake is a bad trade at 2–4× cost.

Separately, the root `CLAUDE.md` records `correctness-review` + `test-review`
catching real defects that a green 71-test suite missed (#1833) — the *risk*
lenses earn their place on grounds evidence can't cheapen.

### Proposed tiers

**Tier 1 — critical on every code change (risk gates):**
`security-review`, `correctness-review`, `spec-compliance-review`,
`doc-review`. This is exactly the existing change-size fast-path roster
(`change_size.py` `keepAgents`), and it satisfies the pre-PR hook's ≥2
registered-dispatch floor (#1461/#1886). Two are haiku; the two opus lenses
are the ones whose failure modes are silent and expensive.

**Tier 2 — run when the change can exhibit what they check (trigger-scoped):**

| Lens | Proposed trigger | Mechanism |
| --- | --- | --- |
| arch-review | already gated | keep `change_impact.py` as-is |
| domain-review | architectural/size signal | see below — the largest single win available |
| test-review, test-smell-review | diff touches test files, or adds runtime code with no test change (the coverage-gap case) | `Scope:` globs from `plugins/dev-team/knowledge/test-file-indicators.md` + a `change_shape.py` signal |
| concurrency-review | diff introduces concurrency primitives (async/await, threads, locks, shared mutable module state) | new content-trigger check in `change_shape.py` — a grep-class question, deterministic by definition |
| complexity-review, naming-review, structure-review | any non-fast-path code diff (unchanged) — but see §3 for shrinking their job | — |
| refactor-opportunity-review | demote from `Scope: always` to `/build`'s REFACTOR checkpoint + on-demand | its charter is the post-GREEN TDD phase; in the `/code-review` panel it overlaps structure-/complexity-review |

**Tier 3 — repo-wide trend lenses, never per-diff:** already done
(`/repo-review`'s fixed four). No change.

### The domain-review decision

`domain-review` is the only always-on opus lens with no gate. The skill
excluded it from the architectural-impact gate deliberately — a body-only
edit can put business logic in a controller, which is a real domain finding
with zero structural signal — and required that widening `GATED_LENSES` cite
measured per-lens data (#1624), not intuition. That discipline is right.
Concretely:

1. **Measure first:** `review-value.jsonl` rows already record per-round
   agents and finding counts. Once ≥10 review runs are logged,
   `/harness-audit` steps 3.2–3.4 will say whether domain-review is a
   zero-fail, high-suggestion-share, or high-dismissal lens.
2. **If the data supports it,** the cheapest correct moves in order: (a) add
   it to the change-size fast path's *drop* set explicitly (it already is
   dropped there — confirm the data agrees), (b) add a domain-signal trigger
   (files under domain/model/service layers, or any diff ≥ N lines), (c)
   tier the model down — with an `/agent-eval` fixture run before and after,
   per `plugins/dev-team/knowledge/verification-mode.md`'s evidence-first
   rule for tier-downs.

### The uniform-`effort: high` lever

All 46 agents declare `effort: high`. Reasoning effort is a second pricing
axis independent of model tier, and it is currently unused as a control.
Verification-mode re-dispatches already tier down; first-pass dispatches
don't. Candidates for `effort: medium` where the lens is
checklist-shaped rather than judgment-shaped: `spec-compliance-review`,
`doc-review`, the glob lenses (a11y, js-fp, reactivity). Same
evidence rule: change one lens at a time and re-run its eval fixtures
(`/agent-eval`) before shipping the tier-down.

---

## 3. Moving agent work into scripts and open-source tools

The governing rule already exists (root `CLAUDE.md`: *deterministic tools
over inference*), and the injection pipeline already exists (the
static-analysis pre-pass dedups findings into every agent's prompt with
"do not re-report"). What's missing is coverage: **no complexity tool and no
duplication tool is integrated anywhere in the pre-pass**, while two
always-on sonnet lenses re-derive exactly those numbers by inference on
every run.

### Highest-leverage additions (new Tier-1 static-analysis lanes)

| Gap | OSS tool | Displaces | Notes |
| --- | --- | --- | --- |
| Cyclomatic complexity, nesting depth, function length, parameter count | **lizard** (multi-language, one pip install) — or radon/xenon (Python), ESLint `complexity`/`max-depth`/`max-params`/`max-lines-per-function` (JS/TS) | The entire mechanical checklist of `complexity-review` | The agent's four headline checks are all mechanically computable. After integration, complexity-review's residue is judgment ("is this complexity essential or accidental?") — a candidate for haiku + `effort: medium`, or for folding into structure-review. This is the single cleanest agent→tool transfer available. |
| Copy-paste / syntactic duplication | **jscpd** (multi-language) or PMD CPD | The DRY half of `structure-review`; part of `refactor-opportunity-review` | Keep `plugins/dev-team/skills/semantic-duplication-scan/SKILL.md` for what linters can't see (semantic duplication) — that division is already documented in the skill. |
| Naming conventions + magic values | ruff pep8-naming (`N`) + `PLR2004`; ESLint `naming-convention`, `no-magic-numbers` | The convention half of `naming-review` | Residue: intent-revealing-name judgment. Supports a naming-review tier-down. |
| Static a11y checks | axe-core / eslint-plugin-jsx-a11y | The mechanical half of `a11y-review` | Agent keeps focus-management/flow judgment. |
| Performance anti-patterns | semgrep performance rulesets; Repowise `get_health` static I/O-in-loop / N+1 findings injected as pre-pass context rather than agent-fetched | Part of `performance-review` | Repowise already computes these findings; today the agent has to go look. |

All of these are additive and safe by construction: the pre-pass never gates
(`status: skip` when a tool is absent), SARIF/JSON adapters are the
established pattern (≤40-LOC bespoke adapters per
`plugins/dev-team/skills/static-analysis-integration/references/tool-configs.md`),
and dedup precedence already ranks deterministic findings above agent output.

### Second-order moves

- **Grow `repo_invariants.py` deliberately.** The mechanism (#1608) exists
  precisely so mechanically-checkable repo facts stop being re-derived once
  per agent per round. Adopt the working rule: any finding class an agent
  reports for the second time, where the check is expressible as a
  script, becomes a `CHECKS` entry in the same PR that fixes the finding.
- **Content triggers as deterministic dispatch decisions.** The
  concurrency-primitive trigger (§2) and a test-file-touch signal belong in
  `change_shape.py`, not in orchestrator judgment — same category as the
  existing `hasRuntimeSurface`/`isTestOnly` fields, one of which
  (`isTestOnly`, #1964) is already computed and waiting for a consumer.
- **Close the harness-audit seam.** `/harness-audit` measures agents against
  usage data but has no criterion of the form *"this lens's applied findings
  are a subset of what an integrated deterministic tool reported."* Once
  lizard/jscpd findings flow through the pre-pass, `review-value.jsonl`
  rounds make that comparison computable — add it as a drop-candidate
  criterion so agent-vs-tool redundancy is detected by mechanism rather
  than re-litigated by intuition.
- **Pre-flight secret scan.** Step 2 greps a single hardcoded-key pattern;
  gitleaks is already a Tier-1 pre-pass tool. Prefer gitleaks in pre-flight
  when installed, keeping the grep as the zero-dependency fallback.

---

## 4. Sequencing

**Now (no new evidence needed — additive or config-only):**

1. Add lizard + jscpd as Tier-1 static-analysis lanes with adapters;
   inject via the existing pre-pass.
2. Add the concurrency-primitive content trigger to `change_shape.py`; scope
   `concurrency-review` to it.
3. Demote `refactor-opportunity-review` from `Scope: always` to
   `/build`-checkpoint + on-demand.
4. Switch pre-flight secret scan to gitleaks-when-available.
5. Scope `test-smell-review` to test-file-touching diffs via `Scope:` globs
   (test-review keeps `always` — its coverage-gap check needs to see
   production diffs that *lack* test changes).

**Next (needs the data the harness already collects):**

6. Accumulate ≥10 logged review runs; run `/harness-audit`. Act on its
   zero-fail / low-value / over-tiered outputs — domain-review gating is
   decided here, not by fiat.
7. Per-lens `effort: medium` tier-downs, one at a time, each backed by an
   `/agent-eval` before/after run.
8. After lizard/jscpd data flows: shrink complexity-review's charter to the
   judgment residue (or fold it into structure-review) and add the
   agent-vs-tool redundancy criterion to `/harness-audit`.

**Expected effect.** Steps 1–5 remove two always-on lens dispatches
(refactor-opportunity, concurrency on most diffs), narrow one more
(test-smell), and convert the most token-hungry mechanical checklists into
one-time tool runs whose findings are shared across all remaining agents.
Steps 6–8 address the four-opus-lens concentration, where the per-token
prices say most of the money is — with the eval fixtures as the regression
net that makes tier-downs safe to attempt.
