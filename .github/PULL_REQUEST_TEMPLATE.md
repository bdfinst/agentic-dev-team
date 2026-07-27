<!--
PR title must be a conventional-commit line — this repo squash-merges, so the
title becomes the commit message: <type>(<scope>): <description>.

Docs-only PRs (touching only *.md, .gitignore, LICENSE — no code, agent,
skill, hook, eval fixture, or marketplace manifest) may arm `gh pr merge
--auto --squash` at open time. Anything else needs explicit human merge.
-->

## Summary

- <what changed and why, 1-3 bullets>

## Test Plan

- [ ] <verification step 1>
- [ ] <verification step 2>

<!--
One line per issue this PR resolves, using a real closing keyword (Closes,
Fixes, Resolves). For an epic issue this PR only contributes a slice of, use
"Part of #<epic>" instead — a non-closing reference, since epics don't
auto-close when a sub-issue's PR merges (see epic-auto-close.yml, #987).

Never phrase a non-closing reference with a closing keyword, even negated —
GitHub's parser fires on "fixes #123" regardless of surrounding words like
"does not" or "won't" (issue #977).
-->

Closes #
