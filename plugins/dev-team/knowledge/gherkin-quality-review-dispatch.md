# Adversarial Gherkin Quality Review — Dispatch & Aggregation

Shared procedure `/gherkin-derive` (Step 5b) and `/gherkin-public` (Step 4b)
both cite, so the dispatch/aggregation mechanics live in exactly one place
instead of being re-derived near-verbatim in two `SKILL.md` files (issue
#1452). Each calling step states only what's specific to it (when it fires,
what input it passes); everything below is common to both.

## Dispatch

Spawn **two** independent instances of the `gherkin-quality-critic` agent as
parallel subagents in a single message, using the `Agent` tool — the same
"Spawn agents as parallel subagents in a single message using the Agent
tool" convention `../skills/code-review/SKILL.md` already documents. Both instances
receive the identical input (the `.feature` file(s) plus each surface's cited
source); neither instance's prompt may contain the other's output — that is
the entire point of running two, and it is a structural property of the
dispatch (one message, two calls, read neither result until both are issued),
not a runtime check.

**Why two instances of the same agent, not two distinct critics?** Every
other multi-agent review point in this fleet (`/plan` step 5b's five
plan-review-* critics, `/code-review`'s reviewer panel) dispatches **distinct**
agents with distinct scopes. This is deliberately different: `gaps` and
`balance_issues` are two facets of one judgment call (does this scenario set
adequately exercise the cited source?), not two independent concerns that
split cleanly across separate personas the way plan-review's acceptance/
design/parallelization/strategic/ux critics do. Running two instances of the
*same* narrow agent gets ensemble/self-consistency corroboration on that one
judgment call for the cost of a second call, instead of building a second
persona with an artificial scope boundary. Splitting `gaps` and
`balance_issues` into two distinct critics remains the fallback if the two
checks are ever shown to need materially different review lenses.

## Aggregation

The calling skill performs the fold itself — no third agent, mirroring how
`/code-review` aggregates its panel's JSON without a meta-agent. Match each
instance's `gaps`/`balance_issues` entries by the key
**`(feature_file, title)`**:

- A finding present for the same key in **both** instances' output is
  **agreed** — even if the two instances worded the `rationale` differently,
  the same `(feature_file, title)` pair is what makes it agreed.
- A finding present in only **one** instance's output for a given key is
  **single-source (unconfirmed)**.

The fold is exact-string, not fuzzy — its accuracy depends on both instances
wording a shared finding's `title` identically. The agent is instructed to
word `title` to match the cited `Feature:`/`Scenario:` heading text
**verbatim** wherever possible, which keeps the common case (the finding is
about a specific, already-named scenario) exact. The accepted, known gap:
two instances phrasing the same *novel* finding (e.g. a missing scenario that
has no existing heading to anchor to) with slightly different wording will
fold as two single-source findings rather than one agreed finding — this is
a false negative on "agreed," not a false positive, so it only ever
under-promotes confidence, never over-promotes it.

## Failure handling

If either `Agent` call errors, times out, or returns output that cannot be
parsed as the agent's documented JSON schema:

- Treat that instance's `gaps`/`balance_issues` as empty — never crash the
  skill run over one instance's failure.
- Never promote the absence of a matching finding from the failed instance
  into a false "agreed" classification, and never silently drop the note
  that a failure happened.
- The report must state explicitly: *"one review instance did not return
  usable output — findings below are single-source only."*
- If **both** instances fail, both new report sections print
  `Both review instances failed to return usable output — no Gherkin quality
  findings available for this run.` instead of the two per-finding sections.

## Zero-findings state

Both report sections — "Agreed Gherkin quality findings" and "Single-source
(unconfirmed) Gherkin quality findings" — **always print**, even when a
bucket is empty, so the section's presence in a report is predictable for
tooling/tests, not conditional on there being something to say:

```
Agreed Gherkin quality findings
  None — both instances raised no findings.

Single-source (unconfirmed) Gherkin quality findings
  None — both instances raised no findings.
```

## Report section format

Each calling skill's report step prints two sections, distinct from every
other callout in that step — this is semantic gap/balance judgment from an
independent reviewer, never folded into a structural-presence check:

- **"Agreed Gherkin quality findings"** — every `(feature_file, title)` pair
  both `gherkin-quality-critic` instances raised, one line each:
  `<feature_file>:<title> — <rationale>`. Per the zero-findings state above,
  print `None — both instances raised no findings.` when this bucket is
  empty — never omit the section itself.
- **"Single-source (unconfirmed) Gherkin quality findings"** — every pair
  only one instance raised, same line format, explicitly labeled unconfirmed
  (never elevated to the same confidence as an agreed finding). Same
  zero-findings rule applies. If either review instance failed or returned
  unparseable output, state that here per the failure-handling rule above,
  rather than silently treating it as "no findings."

## Runtime isolation check

The mutual-blindness property above — "one message, two calls, read neither
result until both are issued" — is asserted only in this doc's prose and in
content-guards that check the markdown *says* the right thing; nothing runs
two real dispatches and checks isolation held at runtime.
`${CLAUDE_PLUGIN_ROOT}/scripts/verify_gherkin_quality_critic_isolation.py` closes that gap: it
dispatches the real `gherkin-quality-critic` agent twice via two fully
independent `claude -p` subprocess calls, each against a fixture carrying its
own randomly-generated canary marker, and fails if either transcript contains
the *other* dispatch's canary. Like `evals/README.md`'s live eval gate, it is
**opt-in and paid** (needs the `claude` CLI + `ANTHROPIC_API_KEY`) and
**fails open** — missing credentials print a skip message and exit 0, never a
failure. It is not wired into any CI workflow by default. Run it locally:

```bash
ANTHROPIC_API_KEY=sk-... python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_gherkin_quality_critic_isolation.py"
```

## Scope of this doc

This doc owns the dispatch/aggregation/failure/zero-findings mechanics and
the report section format above. It does not own: when a calling skill
decides to dispatch at all, or what a calling skill's report step must
distinguish these sections from (each `SKILL.md`'s own Step 5b/4b states its
skip conditions; each report step names the other callouts these sections
must stay distinct from — `gherkin-derive`'s characterization/possibly-stale
callouts, `gherkin-public`'s hand-authoring-flagged-components callout).
