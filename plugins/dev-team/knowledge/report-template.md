# Report Template

Shared header/footer/empty-section contract for dev-team's ~15
report-writing skills (`test-health`, `cd-test-architecture`,
`competitive-analysis`, `docker-image-audit`, `test-improve`,
`harness-audit`, `session-review`, `explore`, `test-design`,
`frontend-architecture`, `agent-eval`, and others) to adopt over time.
Generalized from `test-improve`'s Phase 9 template
(`skills/test-improve/templates/executive-summary.md`), the most complete
existing example in the plugin — same role as `knowledge/review-template.md`
plays for code-review agents, but for standalone reports rather than the
review aggregation step.

**Adoption status**: only `test-health`, `cd-test-architecture`, and
`competitive-analysis` have migrated onto this contract so far. Every other
skill named above — including `docker-image-audit`, which still uses its own
unrelated local template at `skills/docker-image-audit/references/report-template.md`
(same filename, different, non-conforming structure), and `test-improve`,
which keeps its own local `skills/test-improve/templates/executive-summary.md`
body — has **not** adopted this contract yet; being named above is a
statement of intended scope, not current compliance.

**Scope**: this file defines the shared header, closing Provenance section,
and empty-section rule only. Skill-specific body content — findings tables,
per-skill scoring, detail sections — stays local to each skill's own Output
section. A skill's Output section references this file for the shared parts
instead of inlining its own; see the Reference sentence below.

## Reference sentence

Every report-writing skill that adopts this contract points at it with this
exact sentence, so the reference reads identically across skills instead of
being reworded per skill:

> For the header block and closing Provenance section, follow
> `knowledge/report-template.md`; the sections below are this skill's own
> body.

## Header block

Every report opens with:

```markdown
# <Report Title> — <target> (<date>)

**Date**: <ISO 8601>
**Target**: <repo / image / component / scope of comparison>
**Tool versions**: <relevant tool versions, e.g. coverage tool, mutation tool — omit fields with no applicable tool>
**Scope**: <what was analyzed — full repo, --path <dir>, single component, etc.>
```

Skills with an existing single-line summary convention (e.g. `## Test Health
— <repo> (<date>)`, `**Shape**: ... **Fit**: ...`) keep that line as their
own body content — it is not replaced by this header block, only preceded
by it.

## Empty-section rule

Scope: **header/footer fields only** — the fields in the Header block above
and the Provenance section below. A header/footer field with no value
renders `_Not applicable — <reason>._` rather than being silently omitted
(e.g. `**Tool versions**: _Not applicable — no coverage tool detected._`).

This rule does not govern skill-specific body content. A skill's own
body-level empty-value conventions are unaffected and are not required to
follow this rule — for example, `test-health`'s Farley Score row uses its
own convention (verbatim scope-labelled value, or the literal `no in-scope
test files`) rather than the generic `_Not applicable_` phrasing.

## Default section ordering

For a **new** report-writing skill with no established structure of its own,
default to this ordering:

1. Header block
2. Executive Summary
3. Findings / Detail (skill-specific)
4. Next Actions
5. Provenance (closing section, below)

This ordering is **illustrative guidance for new skills only**. It is not
grounds to rename an existing report-writing skill's established section
headings (e.g. `cd-test-architecture`'s `### Next steps`, `competitive-
analysis`'s `## Next Steps`) to match this ordering's example names when
migrating that skill onto this shared contract — a migrated skill's body
stays exactly as it already is.

## Provenance (closing section)

Every report closes with a Provenance section, generalized from
`test-improve`'s Phase 9 §10:

```markdown
## Provenance

- Repository: `<repo path>`
- Branch / SHA: `<branch>` / `<sha>`
- Run parameters: `<flags, scope, or other invocation parameters>`
- `dev-team` plugin version: `<plugin_version>`
```

Omit fields that don't apply to a given skill (e.g. a skill with no
run-scoping flags), applying the empty-section rule above rather than
deleting the field.

## Related

- `knowledge/review-template.md` — the equivalent shared contract for
  code-review agents' aggregation step.
- `knowledge/report-to-pdf.md` — rendering any report produced under this
  contract to PDF.
- `skills/test-improve/templates/executive-summary.md` — the precedent this
  contract generalizes from; `test-improve` keeps its own local template body
  unchanged and is not required to migrate onto this file.
