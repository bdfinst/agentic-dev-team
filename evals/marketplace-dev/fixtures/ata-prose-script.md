# Use-case: catalog version-sync check

We need a capability that, for every plugin in a marketplace monorepo, reads the
plugin's own `plugin.json` version and asserts it equals the `version` and
`source.ref` recorded for that plugin in `.claude-plugin/marketplace.json`. It
reports any drift as a list of `plugin: expected vs actual` mismatches.

This runs in CI on every pull request and as a local pre-push gate. It must
produce identical output for identical input, must not cost model tokens, and
its result gates the merge.
