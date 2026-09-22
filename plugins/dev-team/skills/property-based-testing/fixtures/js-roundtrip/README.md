# fast-check round-trip fixture (#2190)

Minimal JS fixture project for `/property-based-testing`'s fast-check
(JS/TS) path, documented in
[`../../references/languages/javascript.md`](../../references/languages/javascript.md).

- `roundtrip.js` — a pure `encode`/`decode` pair (string reversal; its own
  inverse), the same literal-name round-trip heuristic Python's
  `hypothesis_scaffold.py` looks for, mirrored here for JS/TS.
- `roundtrip.properties.test.js` — the fast-check property test a scaffold
  targeting `encode`/`decode` would generate: `fc.assert(fc.property(...))`
  asserting `decode(encode(x)) === x`.

## Test determinism & the vendoring boundary

`node_modules/fast-check/` and `node_modules/pure-rand/` (fast-check's only
dependency) are **vendored and checked into this repo** — `git add -f`, since
the repo-root `.gitignore`'s blanket `node_modules/` rule normally excludes
them and a nested `.gitignore` cannot un-ignore a directory a parent
`.gitignore` already excludes. Both are pure JS with no native/platform
binaries, ~1.8M total, so they're identical on every dev machine and CI
runner — this is what satisfies this skill's "no live install of fast-check
during a test run" determinism requirement.

`vitest` (and its transitive deps) is **not** vendored. Newer vitest pulls
in platform-native binaries (`@rolldown/binding-<platform>`,
`lightningcss-<platform>`) that are specific to the host OS/arch — checking
one platform's build into git would silently break on a maintainer's
different platform (this repo's CI is `ubuntu-*`, but maintainers develop on
macOS — see the repo `CLAUDE.md` "Gates are platform-bound too" note), and
covering every platform would multiply the vendored size for no determinism
benefit `fast-check` itself doesn't already provide. Resolving `vitest` via
`npx vitest run` (or `npm install` first) is project-init's own normal
live-install path for the project's test runner — a repo-level concern this
fixture doesn't re-litigate.

## Run

```bash
npm install   # fetches vitest + fast-check/pure-rand (already vendored) if missing
npx vitest run
```
