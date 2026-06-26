# Plan: Close the craftsmanship-axis review gaps

## Origin

Code-review feedback on `~/_git/laser-layout` surfaced four issues our review
agents do not catch. They collapse into **three missing capabilities** on the
language-agnostic review agents. This plan adds the detection rules, keeps them
language-agnostic by construction, and proves both with eval fixtures.

Source examples (TypeScript, but the principles are universal):

- `dedup.ts` `polygonsMatch` — terse names, a `Math.abs(x-y) > tol` idiom
  open-coded 4×, an inline normalize that duplicates the existing
  `translatePolygon` helper. "The algorithm should jump off the page."
- `types.ts` `NestingConfig` — `epic #24`, `#41`, `#43` tracker IDs in comments.
- `polygon.ts` `boundingBox` — manual min/max loop reimplementing `Math.min/max`.
- `polygon.ts` `reflectPolygon` — orphaned doc comment (describes the function
  below it), and `0 - p.x` instead of unary `-p.x`.

## The three gaps and their owners

| Gap | Concept | Owner agent |
|---|---|---|
| **G1 — Reinvent-the-platform** | Hand-rolling a stdlib/built-in or an existing in-repo helper | `refactor-opportunity-review` |
| **G2 — Expressiveness** | A repeated idiom that should be a named predicate; missing intention-revealing intermediates so the algorithm reads top-down | `refactor-opportunity-review` |
| **G3 — Comment hygiene** | Comments must describe *purpose*, not reference issues — flag tracker/epic/ticket IDs in comments; also flag a doc comment detached from the symbol it annotates | `doc-review` |

`refactor-opportunity-review` has **zero eval fixtures today** — extending it
without adding fixtures would leave it unguarded. This plan fixes that too.

## How we keep these language-agnostic

The feedback is TypeScript, but both owner agents are **language-agnostic** (they
run on any file type; `js-fp-review` is the JS/TS-only one and self-skips). Five
design rules keep the new capabilities agnostic by construction:

1. **State each rule as a principle, not a regex.** "Don't reinvent the
   platform", "extract the repeated idiom", "no tracker IDs in comments" are
   language-neutral. The agent recognizes the *concept*, then maps it to the
   local language — it does not pattern-match TS syntax.

2. **Per-language signals live in `knowledge/design-smells.md`, not the agent
   body.** Add a small "reinvented built-in" cheat-sheet keyed by language so the
   agent reads it the way it already reads the smell→pattern table. Adding a
   language becomes a knowledge edit, not an agent edit, and the agent body stays
   under its token budget.

   | Language | Hand-rolled → built-in (examples) |
   |---|---|
   | JS/TS | min/max loop → `Math.min/max`; accumulator → `reduce`; `0 - x` → `-x`; copy loop → spread/`slice` |
   | Python | min/max loop → `min()/max()`; accumulator → `sum()`; reimplemented `itertools`/`collections` |
   | Java | loop → `Stream.min/max`, `Collectors`; `Math.max` |
   | C# | loop → LINQ `Min/Max/Sum/Aggregate` |
   | Go | loop → `min`/`max` built-ins **(Go 1.21+ only)**, `slices`/`maps` pkgs |

3. **Put the rules on the agnostic agents, never on `js-fp-review`.** This is the
   architectural decision that makes them fire across languages. G3's comment
   scan works on any comment delimiter (`//`, `#`, `/* */`, `--`, `<!-- -->`);
   doc-review already operates on comments language-agnostically.

4. **Calibrate "What NOT to flag" against version/idiom drift.** Only flag a
   reinvented built-in when (a) the built-in demonstrably exists in the project's
   language/version (manual min/max in **Go < 1.21** is idiomatic and correct —
   do not flag), and (b) the hand-rolled form is not a documented hot-path
   optimization. When unsure → confidence `none`, do not flag. All G1/G2 findings
   are **`suggestion`** severity, never `error` — this is a taste axis.

5. **Prove agnosticism in the corpus.** Ship parallel fixtures in ≥2 languages
   for the mechanical gaps (done: TS + Python for G1 and G3).

## Eval fixtures (created — currently RED)

These encode the desired post-implementation behavior; they fail today and turn
green when the agent edits land (TDD for agents).

| Fixture | Agent | Grade | Proves |
|---|---|---|---|
| `ro-reinvented-builtins.ts` | refactor-opportunity | warn | G1 (TS) |
| `ro-reinvented-builtins-py.py` | refactor-opportunity | warn | G1 (Python — agnostic) |
| `ro-uses-builtins.ts` | refactor-opportunity | pass | G1 no over-fire |
| `ro-repeated-idiom.ts` | refactor-opportunity | warn | G2 |
| `dr-tracker-ids-in-comments.ts` | doc-review | warn | G3 tracker IDs (TS) |
| `dr-tracker-ids-py.py` | doc-review | warn | G3 tracker IDs (Python — agnostic) |
| `dr-clean-inline-comments.ts` | doc-review | pass | G3 no over-fire |
| `dr-orphaned-doc-comment.ts` | doc-review | fail | G3 detached doc comment (misdescribing docs → `fail` per doc-review rubric) |

## Status

**Implemented and validated** on branch `review-craftsmanship-gaps`. `eval_grade.py`
graded **10/10 pairs PASS** — the 8 new fixtures green, plus the 2 pre-existing
`doc-review` fixtures (`dr-accurate-docs`, `dr-stale-readme`) still green (no
regression / no over-fire). The reviewers were dispatched against the **edited
working-tree definitions** (the registered plugin resolves to a stale cache
snapshot, so a normal dispatch would have graded the old agents). A standards-
reference guard (`ISO-4217`, `RFC-2119`, …) was added to doc-review after the
regression pass flagged the false-positive risk. Corpus integrity: 91 valid.

## Implementation steps (done)

1. **`knowledge/design-smells.md`** — add a "Reinvented built-in / existing
   helper" smell row + the per-language cheat-sheet table above + a "What NOT to
   flag" note (Go < 1.21, documented hot paths, C without stdlib).
2. **`agents/refactor-opportunity-review.md`** — add G1 + G2 to Detect as
   `suggestion`-severity rules citing `design-smells`; add the two self-challenge
   questions (version check; only-adds-a-name check). Stay under the 40-line body
   budget; add `design-smells` to `cites:`.
3. **`agents/doc-review.md`** — add G3 to "Inline comment drift" on the principle
   *comments describe purpose, not issues*: tracker-ID bleed (`#\d+`,
   `[A-Z]{2,}-\d+`, epic/ticket/story near a number) and detached doc comments;
   `suggestion` severity. The suggested fix is to **rewrite the comment to state
   intent and move the issue reference to the commit message**, not merely delete
   the number — a comment whose only content is a ticket pointer should be
   replaced by one that explains *why*.
4. **Registry/citation sync** — refactor-opportunity's new `cites:` must resolve;
   run `scripts/citation_lint.py`.
5. **Validate** — `/agent-eval --agent refactor-opportunity-review` and
   `--agent doc-review`. The 8 new fixtures must go green; the existing corpus
   must stay green (no regressions / over-fire).
6. **Ship** — these touch shipped agents, so: feature branch + PR, **human
   merge** (not doc-only auto-merge).

## Out of scope

- The `0 - p.x` micro-idiom is covered as a G1 example only; not its own rule.
- Naming of `bbA`/`normA` is already `naming-review`'s job — not duplicated here.
