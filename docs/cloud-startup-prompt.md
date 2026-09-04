# Cloud startup prompt

The Setup script ([`.claude/cloud-setup.sh`](https://github.com/bdfinst/agentic-dev-team/blob/main/.claude/cloud-setup.sh)) provisions
the machine. This is the other half: the **first message** to send in a fresh
cloud session, so Claude confirms the environment is actually sound before it
starts changing code.

Provisioning and verification are separate concerns on purpose. The Setup script
runs pre-boot and **must** exit 0 — a non-zero exit fails session startup — so it
can only *report* a broken toolchain, never refuse to hand one over. This prompt
is what makes the session act on that report.

## Why bother

A provisioning run can finish, print green checkmarks, and still leave a
container where `semgrep --version` aborts. That exact thing happened: a
distro-packaged PyJWT that `pip` could not uninstall left `semgrep` importing a
`cryptography` whose Rust bindings could not load. `command -v semgrep`
succeeded throughout. The damage showed up much later and in a shape that
pointed nowhere near the cause — every `plugins/security-assessment/` rule
silently matched nothing, and the fixture audit failed with 27 rules reported as
NO-FIRE.

Ten seconds of exercising the tools up front is cheaper than diagnosing that
from the far end.

## The prompt

Paste this as the first message of a new cloud session:

```text
Before doing any task work, verify this environment is sound and report honestly.

1. Run: python3 scripts/verify_toolchain.py
   It executes each tool rather than checking PATH, so it catches a tool that is
   installed but cannot start. If any REQUIRED tool fails, fix it before
   continuing and tell me what you did. Known repair, if semgrep fails with a
   _cffi_backend or cryptography error:
       python3 -m pip install --user --force-reinstall cffi cryptography

2. Confirm the git hooks are live: `test -f node_modules/.bin/husky`. If missing,
   run `npm ci` — without it, pre-commit and pre-push silently do nothing and
   scripts/ci-local.sh is the only thing standing between a bad commit and main.

3. Confirm the dev-team plugin loaded THIS session (the SessionStart hook is too
   late — its install lands next session):
       claude -p "List the names of every skill available to you, one per line." \
         --max-turns 1 | grep -c '^dev-team:'
   Expect a non-zero count (~86). Zero means the Setup script did not run or the
   plugin install was blocked; say so rather than proceeding as if skills exist.

4. Establish a baseline before you change anything: run `bash scripts/ci-local.sh`
   and tell me the result. If something is already red on a clean tree, that is
   pre-existing — report it, do not silently absorb it into my change, and do not
   try to fix it unless I ask.

Then state clearly: what works, what does not, and what you repaired. Do not
start the task until you have reported. If any of the above cannot be completed,
say which and why rather than continuing quietly.
```

## Cutting it down

The prompt is long because each step earned its place. If you want a one-liner
for a session where you only intend to read code, this is the load-bearing part:

```text
Run `python3 scripts/verify_toolchain.py` first and report the result. It executes
each tool instead of probing PATH, so it catches installed-but-broken tools. Fix
any REQUIRED failure before starting, and tell me what you repaired.
```

## Making it automatic

To skip the pasting, put the same instruction in the environment's system prompt
or a `SessionStart` hook. Two caveats if you do:

- A `SessionStart` hook runs *after* Claude boots, so it cannot fix the
  plugin-loading problem in step 3 — that one genuinely needs the Setup script.
- Keep it fail-open and time-boxed, like the hooks already registered in
  [`.claude/settings.json`](https://github.com/bdfinst/agentic-dev-team/blob/main/.claude/settings.json). A verification step that
  hangs session startup is worse than the drift it was guarding against.

## See also

- [`cloud-setup.md`](cloud-setup.md) — the Setup script itself, plugin freshness,
  and the snapshot/caching behavior that pins stale plugin versions.
- [`.claude/cloud-setup.sh`](https://github.com/bdfinst/agentic-dev-team/blob/main/.claude/cloud-setup.sh) — what to paste into
  claude.ai/code → Environment → Setup script.
- [`scripts/verify_toolchain.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/scripts/verify_toolchain.py) — the verifier,
  runnable on its own at any time (`--quiet` for failures only, `--json` to script it).
