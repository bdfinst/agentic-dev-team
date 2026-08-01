# 32. Shipped-script path-resolution taxonomy

Date: 2026-08-01

## Status

Accepted

## Context

Issues #1636 and #1637 fixed shipped agents/skills naming scripts by paths
that don't resolve on an install — four agents' `Implemented by:` lines
pointing at repo-root `scripts/` (which doesn't exist in an installed plugin
cache) and six skills invoking scripts by bare relative paths that only
happened to resolve from this monorepo's own working directory. Fixing those
required deciding, case by case, whether a given skill's reference to a given
script was a real defect or a deliberate design choice — and that judgment
call had no single place recording it. The reasoning ended up scattered
across two test files' docstrings (`tests/repo/test_agent_implemented_by_
resolves.py`'s `INTENTIONAL_BARE_INVOCATION`/`INTENTIONAL_WORKTREE_RELATIVE`
sets, `tests/repo/test_shipped_script_refs.py`'s allowlist) and a growing
pile of per-skill "Monorepo-relative by design (#1637)" prose notes, with no
ADR tying the underlying rule together.

The gap surfaced again in #1650/#1651/#1652/#1653 (this same PR's own
predecessors): each fix required re-deriving the same judgment — does this
script ship, and if so, does the invoking skill still have a legitimate
reason to reference it by a path other than `${CLAUDE_PLUGIN_ROOT}/...`? —
from first principles, because there was nowhere to look it up.

There's also a real precedent worth recording as a **rejected alternative**,
not an oversight: plugin-authoring tooling (`agent-create`,
`agent-skill-authoring`, `agent-add`, `agent-remove`, `add-plugin`, and a
generalized `/plugin-audit`) was *relocated* out of dev-team into a
standalone `marketplace-dev` plugin rather than exempted in place. Category 2
below is, in effect, choosing exemption over relocation for a different class
of monorepo-only tooling (individual scripts inside otherwise-shipped
skills, not whole skills) — a deliberate choice, addressed under
"Alternatives considered."

## The taxonomy

Every script a shipped `SKILL.md` or agent file references falls into exactly
one of these categories. The question that decides which: **does the script
ship inside `plugins/dev-team/`, and if so, is `${CLAUDE_PLUGIN_ROOT}`-relative
resolution actually the right semantics for this invocation?**

### 1. Shipped and portable

The script lives under `plugins/dev-team/scripts/` (or `hooks/`), and the
invoking skill references it as `${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py` (or
the quoted equivalent, `"$CLAUDE_PLUGIN_ROOT/scripts/<name>.py"` — house style
per ADR 0033). This is the common case, and what #1636/#1637 fixed
most invocations into. `eval_ablation.py` (#1653) is the most recent addition:
moved from repo-root into the plugin specifically so its `--find-latest`
mode — a generic JSONL reader with no repo-shape assumption — could be
invoked this way from `harness-audit`.

**Sub-case: shipped, but deliberately still cwd/worktree-relative.**
`verify_tier.py` ships under `plugins/dev-team/scripts/`, but
`agent-audit/SKILL.md` invokes it as bare `plugins/dev-team/scripts/
verify_tier.py`, not `${CLAUDE_PLUGIN_ROOT}`-qualified — tracked separately in
`INTENTIONAL_WORKTREE_RELATIVE`. Its whole job is auditing the agents in the
**operator's current working tree**; `${CLAUDE_PLUGIN_ROOT}/scripts/
verify_tier.py` would silently audit the installed plugin cache's own
(possibly stale) copy of itself instead, since the script resolves its
target via `Path(__file__).resolve().parents[1] / "agents"` — relative to
wherever it's invoked FROM, not to what it inspects. Shipping the file
doesn't automatically mean every invocation of it should be
`${CLAUDE_PLUGIN_ROOT}`-qualified; the qualification is correct only when the
invocation's target is itself the plugin's own installed content, not the
user's project.

### 2. Monorepo-only by design

The script only exists at this repo's root (or `evals/`, `metrics/` — its
own checkout-relative tooling), and the invoking skill's whole job is
self-referential to this marketplace repo's own tree: registry sync
(`check_registry_sync.py`, `validate_agent_contract.py`), eval-corpus
tooling (`eval_cache.py`, `eval_variance.py`, `run_integration_eval.py`,
`citation_lint.py` — all read `evals/`, explicitly not shipped per this
repo's own `CLAUDE.md`), or harness-effectiveness auditing.
`${CLAUDE_PLUGIN_ROOT}` would either point at a nonexistent file or, worse,
at a stale installed copy instead of the working tree being audited — the
same hazard the category-1 sub-case above closes for `verify_tier.py`, just
for a script that doesn't ship at all rather than one that does.

Tracked, per-script (not per-skill), in `INTENTIONAL_BARE_INVOCATION` — a
skill in that set that later grows an unrelated bare invocation of a script
that DOES ship is still caught by the main guard, since the exemption is
keyed on the `(skill, script)` pair, not the whole skill. Each premise —
"the script genuinely doesn't ship" — is checked mechanically by
`test_intentional_bare_invocation_pairs_do_not_ship_in_the_plugin`, not
trusted by comment alone. Each entry's `SKILL.md` also carries a
"Monorepo-relative by design (#1637)" prose note near the invocation, so a
reader doesn't mistake the bare path for an oversight.

### 3. Tracked defect

Genuinely unshipped or unqualified, not yet fixed. `KNOWN_BARE_INVOCATION`,
shrink-only, currently empty — the two real defects #1637 found
(`project-init`'s `install-java-static-analysis.py`,
`stryker-xunit-v2-shim`'s `generate_shim.py`) are fixed, and everything
remaining in the older two-way split was reclassified into category 2 above,
not left here.

### 4. Shipped for copy-out

The script ships under `plugins/dev-team/`, but the invoking doc's whole
point is instructing the OPERATOR to copy it into **their own project**
before running it there — `skills/mutation-testing/references/languages/
csharp-stryker-net.md` tells the reader to copy `csharp_stryker_net_wrapper.py`
(plus its status-loop sibling) into their repo's own `scripts/` directory,
then shows the resulting invocation as a bare `python3 scripts/
csharp_stryker_net_wrapper.py`. That bare path is correct precisely because
the file deliberately no longer lives in the plugin at all once copied —
`${CLAUDE_PLUGIN_ROOT}` would be actively wrong here, not merely
unqualified, since the invocation targets a file that exists only in the
operator's own tree. This differs from categories 1–3: the script DOES ship
(unlike category 2) and the reference is not portable-as-is (unlike category
1), because the reference describes a file at its POST-copy location, not
its shipped one.

Tracked in `tests/repo/test_bare_invocation_wide_scan.py`'s
`INTENTIONAL_WIDE_SCAN_INVOCATIONS` under the `copied-out-by-operator`
category, premise-checked by confirming the doc still instructs the
operator to copy the script into their own project.

## Decision

Adopt this four-category (plus the category-1 sub-case) taxonomy as the
one place the "does this reference need fixing" judgment is recorded, and
require every new bare or non-standard script invocation in a shipped
skill/agent to be classified into it — mechanically, where possible, not by
comment alone:

- `INTENTIONAL_BARE_INVOCATION` — category 2. Reclassify into
  `KNOWN_BARE_INVOCATION` (a real defect) only if the script starts shipping
  under `plugins/dev-team/scripts/`.
- `INTENTIONAL_WORKTREE_RELATIVE` — the category-1 sub-case (ships, but
  deliberately still cwd-relative).
- `KNOWN_BARE_INVOCATION` — category 3, shrink-only, never grown without a
  fix landing in the same PR.
- `INTENTIONAL_WIDE_SCAN_INVOCATIONS`'s `copied-out-by-operator` category —
  category 4 (ships, but the reference describes the file's post-copy
  location in the operator's own project).

The Skills Registry (`plugins/dev-team/CLAUDE.md` and `knowledge/skills-
registry.md`) should disambiguate a skill whose primary purpose is
monorepo-self-referential the same way `/agent-readiness`'s row already
does ("scores your project repo's readiness — not the plugin's own review
agents and routing (for that, use `/harness-audit`)") — a category-2-heavy
skill like `/agent-eval` or `/harness-audit` should read as a
maintainer-only tool at a glance, not merely be correctly coded as one.

## Consequences

- Future #1637-shaped review findings have a name and a bucket to slot into
  immediately, instead of re-deriving the reasoning from scratch per
  instance — the exact gap that made #1650–#1653 each start from zero.
- The mechanical checks (`test_intentional_bare_invocation_pairs_do_not_
  ship_in_the_plugin`, the "Monorepo-relative by design" prose-note check)
  remain the enforcement; this ADR is the rationale they implement, not a
  new gate itself.
- The category-1 sub-case (`verify_tier.py`) is a reminder that "the script
  ships" is necessary but not sufficient for "qualify with
  `${CLAUDE_PLUGIN_ROOT}}`" — the invocation's own semantics (does it target
  the plugin's own content, or the operator's project?) still has to be
  checked per call site.
- Does not itself widen any guard's scope — that is #1655's job (scanning
  `docs/`, `references/`, and more invocation forms) — nor does it convert
  the "Monorepo-relative by design" prose marker into a machine-checkable
  frontmatter field, a further idea raised alongside this taxonomy and left
  for a future pass if the prose-note drift becomes a real problem.

## Alternatives considered

- **Relocate every monorepo-only script into a separate maintainer-tooling
  plugin**, mirroring the `marketplace-dev` precedent for whole skills.
  Rejected for category 2: these are individual scripts embedded inside
  skills that are otherwise genuinely dev-team-shipped
  (`agent-audit`, `harness-audit`, `agent-eval` all have real, portable
  responsibilities beyond their one or two monorepo-only script calls) —
  relocating the whole skill would be disproportionate, and relocating just
  the script would still leave the SAME skill needing to reach across a
  plugin boundary with no shared `${CLAUDE_PLUGIN_ROOT}`-equivalent variable
  spanning two independently-installed plugins, per this file's own
  `agent-eval` note.
- **A single flat allowlist with no taxonomy**, just "these paths are known
  bare, don't flag them." Rejected: this is closer to what existed before
  #1637, and it's exactly what made #1650–#1653 each re-derive the same
  reasoning — a flat list records *that* an exemption exists, not *why*, so
  every reviewer re-litigates the "is this really okay" question from
  scratch.

## References

- Issue #1654 — this ADR's originating issue
- Issues #1636, #1637 — the original path-resolution defects and the guard
  this taxonomy explains
- Issues #1650–#1653 — recent fixes that each re-derived this reasoning
  without a place to look it up
- `tests/repo/test_agent_implemented_by_resolves.py` — `KNOWN_BARE_
  INVOCATION`, `INTENTIONAL_BARE_INVOCATION`, `INTENTIONAL_WORKTREE_
  RELATIVE`
- `tests/repo/test_shipped_script_refs.py` — the `${CLAUDE_PLUGIN_ROOT}`
  resolver and its own allowlist
- `tests/repo/test_bare_invocation_wide_scan.py` — widens this guard past
  `SKILL.md` files (#1655) and tracks category 4 above
- ADR 0033 — the quoting house style this ADR's category 1 forward-references
- `knowledge/skills-registry.md` — `/agent-readiness`'s disambiguation
  precedent
