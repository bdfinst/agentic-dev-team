// Commitlint configuration — enforces Conventional Commits on every commit
// message via the .husky/commit-msg hook. release-please derives versions from
// these types (feat -> minor, fix -> patch, feat!/BREAKING CHANGE -> major), so
// keeping messages conventional is what keeps automated releases working.
//
// NOTE: this guards *local commit messages*. Because the repo rebase-merges,
// every PR commit lands on main verbatim, so each one must be a Conventional
// Commit for release-please to pick it up — the PR title lint workflow
// enforces the same ruleset on the PR title.
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Allow the subject to start with a capital letter (config-conventional
    // otherwise rejects sentence-case subjects).
    'subject-case': [0],
  },
};
