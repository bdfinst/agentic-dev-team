# The predictability check

Loaded on demand by [`../SKILL.md`](../SKILL.md)'s Ambiguity Resolution
Protocol. It runs **between Step A (attempt inference) and Step B (classify)**
— it is a test applied *during* classification, not a separate pass over the
artifacts.

## The failure mode it attacks

The protocol names its own weakness plainly: spec synthesis tends to produce
"decisions that look thorough while encoding the same happy-path assumptions a
direct implementation would make silently." `inferable` is where that failure
lands. An assumption gets waved through because it reads as natural — and
naturalness is explicitly *not* the test.

## The test

For each acceptance criterion, generate **at most one** candidate alternative
outcome — a behavior a reasonable developer might implement instead — and check
whether the spec text rules it out.

- **The source does not rule it out** → `requires-stakeholder-input`, not
  `inferable`.
- **The source rules it out** → stays `inferable`, and the check is recorded as
  passed.

### At most one, evaluated — not always one, manufactured

The check is a tripwire, not an enumeration. Generating several alternatives per
criterion would turn a classification aid into its own analysis phase and
inflate the Ambiguity Log past readability.

"At most one" is deliberate wording. When a criterion is unambiguous enough that
every candidate alternative would be absurd, the check records that **no
plausible alternative exists** and passes. It does not manufacture a bad one to
satisfy a quota — that would produce exactly the false blocks the next section
rejects.

### Plausible, not absurd

DeFOSPAM's equivalent floats deliberately absurd alternatives to provoke
stakeholder correction. That works in an advisory tool whose findings are
suggestions. Here the output flips a **blocking** classification, so an absurd
alternative manufactures a false block — and false blocks are how a gate gets
ignored. The alternative must be one a competent developer could actually ship.

## Recording

**Every outcome is recorded in the Ambiguity Log row, including a pass.**

| Outcome | Recorded as |
|---|---|
| Flipped to `requires-stakeholder-input` | The generated alternative, in the row's rationale — it is the question the human is being asked |
| Stayed `inferable` | The check, marked passed, with the alternative the source ruled out |
| No plausible alternative existed | The check, marked passed, noting that |

An omitted check is indistinguishable from a skipped one. The log is the audit
trail that makes "we asked before building" an artifact rather than an
assertion, so a silent pass would hollow it out.

## Division of labor with `plan-review-acceptance`

That agent already applies binary verifiability — "can two people independently
check this criterion and agree on pass/fail?" — at `blocker` severity, and it
still owns weasel-word detection and per-criterion completeness. This check does
not duplicate it.

**What differs is placement, and placement is the whole point.**
`plan-review-acceptance` runs one stage later, against criteria **we** authored.
Checking our own restatement for predictability cannot catch a source
requirement that was unpredictable *before* we normalised it: by then the
ambiguity is already resolved, and the criterion reads cleanly precisely because
someone picked an interpretation. The earlier placement sees the source text;
the later one structurally cannot.

No new gate, severity scheme, or confidence score — the check only moves items
between the two existing classifications.
