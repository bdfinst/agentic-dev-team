# Shared Review Methodology: Enumerate → Classify → Group

Shared three-phase protocol for review agents whose findings are enumerable
over a fixed set of candidates (identifiers, defect categories, violations)
rather than produced by a single holistic judgment. Cite this file from an
agent's `## Protocol` section rather than restating the phases and their
rationale inline — each citing agent still owns its own domain-specific
detail (which candidates to enumerate, which rules classify them, how to
group them) in its own `## Protocol` section.

Run the review in three phases — enumerate first, classify second, group
third:

## Enumerate

List every candidate in scope before judging any of them — every identifier,
every line, every potential divergence from evident intent, whatever the
agent's domain unit is. Do not decide severity or confidence yet, and do not
stop once a plausible issue is found; the enumeration must cover the full
set of candidates, not just the first few noticed.

## Classify

For each candidate listed in Enumerate, apply the agent's domain-specific
rules to decide whether it is a finding at all, and if so, its severity and
confidence. This is where a candidate is either anchored to a concrete piece
of evidence — a specific identifier, an evident-intent citation, a quoted
line — or dropped, before applying judgment. Classification never happens
during Enumerate: separating the two prevents an early, superficially
plausible candidate from being judged before the full candidate set is even
known.

## Group

Report at the granularity of distinct problems, not one finding per
candidate. When the same underlying issue recurs across several candidates
(the same missing guard copy-pasted into three call sites, several
similarly-named magic values), collapse them into a single finding that
enumerates the instances — never fold genuinely distinct problems into one
finding just to shorten the report. The goal is a finding count proportional
to the number of distinct problems, not to the number of lines or
candidates reviewed.

## Rationale

Running these three phases in strict sequence, rather than judging each
candidate as it's found, exists for three reasons:

1. **It prevents selective attention.** A reviewer that classifies as it
   enumerates tends to stop after the first plausible defect, or fixate on
   the most obvious candidates while the enumeration is still incomplete.
   Separating enumeration from classification forces the full candidate set
   to be listed before any of it is judged.
2. **It anchors each finding to a specific piece of evidence before applying judgment.**
   A finding entered during Classify must point at a
   concrete citation — an identifier, an evident-intent quote, a line — not
   a vague impression carried over from skimming during Enumerate.
3. **It keeps the finding count proportional to the number of distinct problems**
   rather than the number of lines or candidates reviewed. Group
   is what prevents a single recurring issue from ballooning into dozens of
   near-duplicate findings, and prevents genuinely distinct problems from
   being flattened into one.

## Citing this file

An agent citing this file keeps its own `## Protocol` section short: name
the three phases, cite this file for the shared rationale, and describe only
what is domain-specific — what Enumerate lists, what rules Classify applies,
and what Group's collapsing criteria are for that agent's findings.
