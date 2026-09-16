# Extracting a spec from a document someone else wrote

Loaded on demand by [`../SKILL.md`](../SKILL.md) when Step 0 selects **validate
mode**. Authoring mode never reads this file.

## Why extraction needs its own rules

In authoring mode the human drafts and we critique, so the first artifact any
gate sees is one they wrote. In validate mode the source already exists and we
did not help write it: whoever is driving reads it, forms a mental model, and
writes criteria from that model. By the time a gate runs, every ambiguity the
source contained has already been resolved — correctly or not — and the
criteria read cleanly *because* someone picked an interpretation.

The citation rule below is what keeps that resolution visible instead of
invisible.

## Supported inputs

| Input | Handling |
|---|---|
| `.md`, `.txt`, `.pdf` | Read natively |
| A GitHub issue URL | Fetch the issue body |
| `.docx` and anything else `Read` cannot handle | **Refuse**, naming the reason and the conversion to perform |

Never attempt a partial parse of an unsupported format. A half-read
requirements document produces a spec that looks complete and is not.

## What to extract

Populate the same three artifacts authoring mode produces — Intent Description,
Architecture Specification, Acceptance Criteria — from the source's content,
plus the usual Ambiguity Log.

## The citation rule

**Every extracted acceptance criterion carries a citation** to the passage it
came from: a section heading, a line reference, or a short verbatim quote.

**A criterion with no citable passage is an inference, not an extraction**, and
is recorded in the Ambiguity Log as one. It is never presented as though the
source stated it.

Without this, extraction and inference are indistinguishable in the output —
which is the exact failure this mode exists to prevent. A reader of the
resulting spec must be able to tell "the RFP says this" from "we concluded
this", because only the second kind needs checking with a stakeholder.

## Routing

Findings enter the **existing** Ambiguity Resolution Protocol and the existing
Ambiguity Log, classified `inferable` (with rationale) or
`requires-stakeholder-input` (a hard block). No new gate, no new severity
scheme, no confidence score.

A third-party document blocks exactly as hard as an in-house draft. It contains
*more* unresolved ambiguity, not less — weakening the bar here would invert the
protocol's whole purpose.
