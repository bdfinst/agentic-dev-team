# DEV_TEAM_PY_HOOK toggle pattern

During the bash → Python hook migration ([#572]), every hook that has
both a `.sh` and a `.py` implementation ships **both**, and
`plugins/dev-team/settings.json` dispatches between them based on an
env-var flag. This is the parallel-ship mechanism referenced in the
contract at `docs/python-hook-contract.md`.

## The flag

For a hook file named `hooks/foo-bar.sh` (or `foo_bar.py`), the toggle is:

```
DEV_TEAM_PY_HOOK_FOO_BAR
```

Rules:

- Prefix is always `DEV_TEAM_PY_HOOK_`.
- Suffix is the hook's base filename **upper-cased with `-` and `.`
  replaced by `_`**. `mutation-testing-smoke-gate.sh` →
  `DEV_TEAM_PY_HOOK_MUTATION_TESTING_SMOKE_GATE`.
- **Default is `0`** (unset counts as `0`). The bash implementation is
  authoritative until the parity harness has been green for at least one
  release-please cycle.
- `1` opts into the Python implementation. Any other value falls back to
  bash.

## The dispatch shape

`settings.json` uses `sh -c` for portability across macOS, Linux, and
Windows Git Bash. Example entry:

```json
{
  "type": "command",
  "command": "sh -c 'if [ \"${DEV_TEAM_PY_HOOK_MUTATION_TESTING_SMOKE_GATE:-0}\" = \"1\" ]; then python3 hooks/mutation_testing_smoke_gate.py; else bash hooks/mutation-testing-smoke-gate.sh; fi'"
}
```

The `sh -c` wrapper isolates the conditional from the hook's own
argument list; stdin/stdout/stderr flow through unchanged.

## Lifecycle

Per-hook lifecycle across the migration:

1. **Phase 0 / Phase 1–3 slice landing.** `.sh` + `.py` both ship; flag
   defaults `0`. Parity harness runs on every fixture in CI. Operators
   can opt into Python in their own environment by exporting the flag.
2. **After one release-please cycle with the flag green in CI.** The
   `.sh` is deleted and `settings.json` is simplified back to a plain
   `python3 hooks/<name>.py` invocation. See `plans/cached-inventing-wave.md`
   Phase 4.

## Why this pattern rather than a global flip

- **Per-hook rollout limits blast radius.** A silent divergence in one
  hook does not roll back every other hook's port.
- **CI can gate on the flag.** The parity harness ships one fixture set
  per hook; a flag lets `DEV_TEAM_PY_HOOK_<NAME>=1 pytest tests/hooks/`
  run the Python path against every non-parity test too.
- **Operators can experiment locally.** A single `export DEV_TEAM_PY_HOOK_FOO=1`
  in their shell rc migrates one hook without touching plugin files.

## Related docs

- [`docs/python-hook-contract.md`](../../../docs/python-hook-contract.md)
  — byte-compatible contract every port must satisfy.
- `plans/cached-inventing-wave.md` — the phased migration plan (#572).
- `plugins/dev-team/tests/hooks/parity/parity.py` — the gate.
