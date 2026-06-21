// Commitlint configuration — enforces Conventional Commits on every commit
// message via the .husky/commit-msg hook. release-please derives versions from
// these types (feat -> minor, fix -> patch, feat!/BREAKING CHANGE -> major), so
// keeping messages conventional is what keeps automated releases working.
//
// NOTE: this guards *local commit messages*. Because the repo merges PRs via
// squash (the squash commit uses the PR *title*), the PR title must also be a
// Conventional Commit for release-please to pick it up — enforce that with a
// PR-title check in CI (e.g. amannn/action-semantic-pull-request).
export default {
  extends: ['@commitlint/config-conventional'],
};
