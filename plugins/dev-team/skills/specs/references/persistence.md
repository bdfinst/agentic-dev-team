# Persisting spec artifacts

Loaded on demand by [`../SKILL.md`](../SKILL.md) once the Cross-Artifact
Consistency Gate passes. Nothing above that gate refers into this file.

After the gate passes, persist all three artifacts plus the verdict so downstream commands (`/plan`, `/build`, spec-compliance-review) can find the spec — chat-only specs are lost between sessions. **Where** they're persisted depends on the project's origin and whether it has opted into the issue-first specs convention.

## Classify where to persist

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/git_origin_host.py` to classify the origin remote: `github` / `other` / `none`.
2. When the result is `github`, additionally run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs_convention_marker.py` to classify the project's root `CLAUDE.md`: `marker` (contains the issue-first-specs opt-in phrase, e.g. "Specs and plans are GitHub issues here, not files") / `no-marker` (file exists, phrase absent) / `none` (no root `CLAUDE.md` found). If it reports `no-marker` or `none`, you MAY still read the root `CLAUDE.md` yourself and apply judgment for an equivalently-worded-but-differently-phrased declaration of the same convention before concluding "no marker" — but this manual-judgment fallback is deliberately unverified by any automated test, unlike the script's literal-match path (see the script's own module docstring).
3. **Branch**:
   - `github` origin **and** a marker found (by the script or by manual judgment) → **Persist to GitHub issue** (below). No downstream consumer of the shipped plugin is silently switched to this path — it requires both an actual GitHub origin and an explicit, repo-declared opt-in.
   - Anything else — non-`github` origin, `none` origin, or a `github` origin with **no** marker found by either path — → **Persist to file** (below). This is today's behavior, unchanged.

## Persist to file

1. **Slugify** the feature name: lowercase, replace spaces with hyphens, strip special characters. ("User Login with MFA" → `user-login-with-mfa`)
2. **Create** `docs/specs/` if missing.
3. **Check** whether `docs/specs/<slug>.md` already exists. If yes, ask: overwrite or create a versioned file (`<slug>-v2.md`)?
4. **Write** using this structure:

```markdown
# Spec: <Feature Name>

## Intent Description
<intent artifact>

## Architecture Specification
<architecture artifact>

## Acceptance Criteria
<acceptance criteria artifact>

## Ambiguity Log

All gap and ambiguity findings from the Ambiguity Resolution Protocol, with their classifications and rationale.

| Decision | Classification | Resolved By | Rationale / Answer |
|----------|---------------|-------------|-------------------|
| <decision text> | `inferable` / `requires-stakeholder-input` | inference / human | <rationale or human's answer> |

## Consistency Gate
- [x/  ] Intent is unambiguous
- [x/  ] Every behavior/goal maps to an acceptance criterion
- [x/  ] Architecture constrains without over-engineering
- [x/  ] Terminology consistent across artifacts
- [x/  ] No contradictions between artifacts
- [x/  ] Every gap/ambiguity finding is logged — inferable with rationale or resolved by human
```

1. **Print** the file path to chat so the user can find it.

## Persist to GitHub issue

**Issue titles are Conventional Commits, not `Spec: <Feature Name>`.** These
issues become epics — their titles seed branch names, PR titles, and (once
their sub-issues land) release versions, so they must pass the same
commitlint ruleset as a commit message (`.github/workflows/issue-title-lint.yml`
enforces this after the fact by labeling `needs-conventional-title`; do not
rely on that backstop — lint proactively, before `gh issue create`, so the
label is never needed). Compose the title as `<type>(spec): <Feature Name>`
— `type` is almost always `feat` (a spec describing new behavior) or `docs`
(a spec that is itself the only deliverable, no code follows); pick
whichever matches the work the spec actually describes, never default
blindly to one. Example: `feat(spec): User Login with MFA`. Verify with
`printf '%s' "<composed title>" | npx commitlint --verbose` before creating
or renaming — if it exits non-zero, fix the title, don't create anyway.

1. **Slugify** the feature name (same rule as above) — used to derive the search query, not a file path or the title itself.
2. **Search** for an existing open issue: `gh issue list --search "<Feature Name> in:title" --state open`. If this call itself exits non-zero, treat it as a hard failure — **never** as "zero matches" (that would risk silently creating a duplicate issue) — report the failure and its cause to chat, and fall back to **Persist to file** above with the already-composed content so the approved spec is never lost.
3. **Branch on the match count**:
   - **Zero matches** → proceed straight to create (step 4).
   - **Exactly one match** → interactive: ask "Found existing issue #N for this spec — update it in place, or create a new one?"; non-interactive (no usable TTY): default to **updating** that single match in place (never create a duplicate) and log the auto-choice.
   - **Two or more matches** → interactive: surface every matching issue and ask which to update, or whether to create a new one instead — never silently pick one; non-interactive: default to **creating** a new issue and explicitly log the ambiguity (which candidate issues it did not act on).
4. **Compose** the issue body using the same structure as the file template above (Intent Description, Architecture Specification, Acceptance Criteria, Ambiguity Log, Consistency Gate), titled `<type>(spec): <Feature Name>` per the rule above.
5. **Create** (`gh issue create --title "<type>(spec): <Feature Name>" --body "<composed body>"`) or **update** (`gh issue edit <N> --body "<composed body>"`) per step 3's decision. Updating an existing issue's body never touches its title — if the existing title predates this convention, rename it too (`gh issue edit <N> --title "..."`) rather than leaving a stale non-conventional title behind.
6. If the create/update call exits non-zero, report the failure and its cause to chat, do **not** claim success, and fall back to **Persist to file** above with the already-composed content.
7. On success, **print** the resulting issue URL to chat — do not write `docs/specs/<slug>.md` on this path.

## Auto-trigger /plan

**Authoring mode only.** The two modes end differently, and deliberately so:

| Mode | Terminal behavior |
|---|---|
| **authoring** | Auto-invoke `/plan`. Do not ask first — the approved spec is the trigger. |
| **validate** | Print the persisted location **and a reason clause**, then offer `/plan` as an explicit next step. Never auto-invoke. |

The auto-trigger's "do not ask first" contract is justified by the human having
just co-authored and approved the spec. Validating a third-party RFP, a vendor
brief, or a competitor's document carries no such commitment — auto-planning it
could be actively wrong, so validate mode stops.

The printed message must name that reason, not just make the offer: a user who
has only ever seen authoring mode will otherwise read the stop as a regression.
Something like *"not auto-invoking /plan: this document wasn't co-authored and
approved with you — run /plan when you're ready."*

In authoring mode, after persisting, automatically invoke `/plan` with the feature description. The plan command discovers the spec artifacts, decomposes the feature into vertical slices, and authors the Gherkin scenarios for each slice.

**Key this off which persistence action actually succeeded, not the "Classify where to persist" decision** — the GitHub-issue path can itself fall back to file (search failure at step 2, or create/update failure at step 6):

- **A file was written** (either "Classify where to persist" chose the file path, or the GitHub-issue path fell back to one): invoke `/plan "<feature description>"` — `/plan` discovers `docs/specs/**` on its own.
- **An issue was created or updated** (step 7 succeeded): invoke `/plan "<feature description>" --spec-issue <issue-url>`, passing that issue's URL. Without this, `/plan`'s own Step 1 (which only searches `docs/specs/**`) would immediately hit its "no specification artifacts found" prompt in the very same run — reintroducing the human interruption this auto-trigger's "do not ask first" contract exists to avoid.
