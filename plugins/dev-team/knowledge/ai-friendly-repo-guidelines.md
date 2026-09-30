# AI-Friendly Repository Guidelines

Rubric of repo conventions that improve Claude Code's effectiveness. Canonical
source for the `/agent-readiness` criteria `D5_claude_md_size`,
`D6_layered_context`, `D7_reference_implementation` and
`B5_composite_check_command`; the scanner's evidence strings link to the anchors
below. Other agents (`claude-setup-review`, `setup`) can cite this file instead
of re-describing the rubric.

These conventions are heuristics: they measure how cheaply an agent can load the
right context and verify its own work, not code quality. The scanner audits only;
it never edits the target repo.

## Layered Context Architecture

Agents pay for every line of always-loaded context and for every wrong guess made
without it. Keep the always-loaded layer small and push detail down to where it
applies.

- **Keep the root `CLAUDE.md` short (about 200 lines or fewer).** Every session
  loads it in full; past the ceiling, rules compete for attention and later ones
  are followed less reliably. Scored by `D5_claude_md_size`.
- **Layer context hierarchically.** Put directory-specific rules in nested
  `CLAUDE.md` files or `.claude/rules/*.md` so they load only when that area is
  touched. Scored by `D6_layered_context`.
- **Move procedures and reference material out of `CLAUDE.md`.** Link to skills,
  knowledge files or docs loaded on demand rather than inlining them.
- **Name a canonical reference implementation.** Point at one well-made module or
  test as the pattern to copy; agents imitate what they are shown. Flagged for
  human review as `D7_reference_implementation` because whether the pointer is
  well chosen is a judgment call.

## Deterministic Verification & Fast Feedback Loops

An agent can only converge on a correct change if it can check its work quickly
and get the same answer every time.

- **Expose one composite check command.** A single `check`, `verify`, `ci` or
  `all` target that runs lint and tests lets the agent verify in one step and
  matches what CI runs. Scored by `B5_composite_check_command`.
- **Make single-target test runs possible.** Running one test file or test by
  name keeps the inner loop seconds long (deferred criterion
  `T4_single_command`).
- **Prefer deterministic checks over model judgment.** A linter, type checker or
  test suite gives a binary answer; use them as the gate before any review agent.
- **Keep the loop fast.** Slow suites get skipped or truncated by agents;
  split slow integration tests from the fast default path.

## Navigable Repository Layout

Agents find code by searching names and paths. A predictable layout reduces the
reads needed to locate the right file.

- **Colocate or mirror tests with source.** A test next to (or at a mirrored path
  of) the code it covers is found in one lookup (follow-up criterion, not yet
  scored).
- **Keep directory depth shallow.** Deep nesting hides files and inflates path
  tokens (follow-up criterion, not yet scored).
- **Use descriptive, conventional names** for files and directories so a grep on
  the domain term lands on the right module.
- **Exclude generated and vendored trees** from search paths so agents do not
  wander into build output.

## Source

Synthesized from Anthropic's published Claude Code guidance on memory files and
verification loops and from this repo's own conventions. Tracked in issue #2178.
