# Directory Enumeration

## The rule

**Never `Read` a directory path to check whether something exists or to see
what it contains.** `Read` expects a file; pointed at a directory it throws
`EISDIR`. This hazard fires whenever an instruction says *what* to detect
("no plan files exist in `plans/`", "no spec artifacts found", "no `agents/`
directory") without saying *how* — the model reaches for the nearest tool
(`Read`) instead of the correct one.

**Use `Glob` for existence checks and enumeration:**

- Existence of a known directory: `Glob(".claude/**")`, `Glob("plans/**")`.
- Enumerating a directory's contents: `Glob("agents/*.md")`,
  `Glob("docs/specs/**/*.md")`.
- Checking for one specific candidate file: a targeted `Read` of that exact
  path is fine (e.g. `Read("docs/specs/foo/spec.md")`) — the hazard is only
  `Read`-ing the *directory itself*, not a known filename inside it.

An empty `Glob` result means "not present" — no directory read is needed to
reach that conclusion.

## Why this is shared, not local

This same hazard has been independently discovered and locally patched three
times (agent-roster enumeration, `--path` target resolution, `## Skip`
existence probing) before this file existed. Citing this file from any
Skip/detection section that implies "check whether X exists" prevents a
fourth local fix.

## How this connects to the rest of the toolkit

Cited by `skills/code-review/SKILL.md` and by review-agent/skill Skip or
detection sections that probe for a directory's presence or contents
(`claude-setup-review`, `progress-guardian`, `spec-compliance-review`, the
`continue` skill) — add a citation here rather than re-explaining the
mechanism inline.
