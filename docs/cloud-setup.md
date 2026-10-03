# Cloud setup: loading the dev-team plugin into a web session

This is the focused recipe for making the `dev-team@bfinster` plugin work in a
**Claude Code on the web** session (claude.ai/code). The plugin works in the
**same** session, not the next one. For the broader walkthrough (including the file-based
fallback), see
[`using-plugin-skills-in-the-web-environment.md`](using-plugin-skills-in-the-web-environment.md).

## Why declaring the plugin isn't enough

Claude loads every skill, agent, and slash command **once, when it starts.**
A plugin is visible only if its files are on disk *before* that happens.
So "install the plugin" means "get the plugin on disk before Claude starts."

That timing is the whole story:

| Mechanism | Runs… | Plugin loads… |
|---|---|---|
| **Setup script** (cloud UI) | **before** Claude boots; filesystem snapshotted & reused | **this** session ✅ |
| **`SessionStart` hook** (`.claude/install-dev-team.sh`) | **after** Claude boots | **next** session only ⚠️ |

The Setup script is the supported way to install software before the session
starts (you cannot replace the underlying machine image). The `SessionStart`
hook runs too late. The plugin it installs takes effect only in the *next*
session. Use the Setup script as your primary path and the hook as a fallback.

The `claude` CLI **is** available in cloud environments, so the install commands
below run from the Setup script.

## The snippet to paste into the Setup script field

claude.ai/code → Environment → **Setup script**. Paste this **delegating**
trampoline. It keeps the UI field stable and lets the real logic live in the
repo. Improvements then ship by merging a PR, not by editing environment
config and forcing a snapshot rebuild:

```bash
#!/bin/bash
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || { echo "[env-setup] cannot cd to $ROOT — skipping setup."; exit 0; }

SETUP="$ROOT/.claude/cloud-setup.sh"
if [ -f "$SETUP" ]; then
  # Always exits 0 by design — a non-zero Setup script FAILS session startup.
  # Read its ✗ lines (from scripts/verify_toolchain.py) for real failures.
  bash "$SETUP"
else
  echo "[env-setup] MISSING: $SETUP — repo hasn't adopted the dev-team cloud setup."
  npm ci || true   # fallback so the husky git hooks still land
fi
exit 0
```

[`.claude/cloud-setup.sh`](https://github.com/bdfinst/agentic-dev-team/blob/main/.claude/cloud-setup.sh) does the actual work.
It installs this repo's test/gate toolchain (`jq`, `shellcheck`, the Python dev deps, `gh`,
`uv`, `mutmut`, `adr`), Node 24+ plus `npm ci` for the git hooks
(`pre-commit`, `pre-push`, `commit-msg`), the plugin install/refresh, and a
closing [`scripts/verify_toolchain.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/scripts/verify_toolchain.py) pass.
The script **refreshes** the plugin (re-pulls the catalog and runs `plugin update`) rather
than only installing. `plugin install` is a no-op once a version is cached, and
the reused snapshot would otherwise pin the first version forever (see
[Keeping the plugin version current](#keeping-the-plugin-version-current)).

Two details to know:

- **`cd "$ROOT"` in the trampoline is not decoration.** Resolving `$ROOT`, using
  it only to locate the script, and then not running `cd` is an easy and quiet
  mistake. `cloud-setup.sh`'s paths are relative and its steps are all
  guarded with `|| true`. From the wrong directory, the script skips everything and
  still prints `cloud setup complete`. The script now resolves and validates its
  own root as a backstop. The `cd` keeps the two independent.
- **Pasting the body of `cloud-setup.sh` directly still works** if you prefer
  not to delegate. Its root resolution validates each candidate against a marker
  file. The script detects that it is running from a pasted temp file and falls back
  to the working directory. You then give up the ship-by-merge property above.

## Verify it worked

The Setup script must `exit 0` even when provisioning went wrong. It can only
*report* a broken toolchain. It can never refuse to hand one over. Two things
close that gap:

- [`scripts/verify_toolchain.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/scripts/verify_toolchain.py) — runs every
  tool instead of probing `PATH`, so an installed-but-unstartable tool fails
  instead of passing. The Setup script calls it at the end. Run it yourself any
  time with `python3 scripts/verify_toolchain.py`.
- [`cloud-startup-prompt.md`](cloud-startup-prompt.md) — the first message to
  send in a fresh session. It makes Claude check the environment (and the baseline
  gate result) before Claude starts changing code.

Then run the headless probe in the session. The probe boots a fresh Claude, lists every
available skill, and counts the `dev-team:*` skills:

```bash
claude -p "List the names of every skill available to you, one per line." \
  --max-turns 1 | grep -c '^dev-team:'
```

| Setup | `dev-team:*` skills | `dev-team:ship` present? |
|---|---|---|
| Plugin installed via **Setup script** (pre-boot) | ~86 | yes ✅ |
| Plugin installed via **`SessionStart` hook** only (post-boot) | 0 (this session) | no ⚠️ |
| No install | 0 | no |

A non-zero count means the plugin loaded this session. (Re-verified in a live
cloud session on 2026-06-21: CLI present at v2.1.185, Setup-script install
yielded 86 `dev-team:*` skills including `dev-team:ship`, loaded same-session.)

## Keeping the plugin version current

Installing once does not keep the plugin current. Three things pin a
stale version:

1. **The environment filesystem is snapshotted and reused**, including
   `~/.claude/plugins/cache/`. The snapshot freezes whatever version installs first
   and hands that version to every later session.
2. **`claude plugin install` is a no-op on an already-installed plugin.** It does
   not upgrade. Also, `marketplace add` on a known marketplace does not re-pull the
   catalog.
3. **Auto-update is off by default**, so the CLI never refreshes on its own.

The fix has three layers, all wired into `.claude/cloud-setup.sh` and the
`.claude/install-dev-team.sh` SessionStart hook:

- **Refresh, don't just install.** Both run `claude plugin marketplace update
  bfinster` and `claude plugin update dev-team@bfinster` on every invocation.
  The SessionStart hook no longer no-ops when a version is already present.
- **Enable marketplace auto-update.** Both call the plugin's own
  [`skills/upgrade/scripts/enable_autoupdate.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/upgrade/scripts/enable_autoupdate.py)
  (`--enable`). The script sets `extraKnownMarketplaces.bfinster.autoUpdate: true` in
  the config `settings.json`. The `/plugin` UI and `/upgrade` toggle the same flag.
  This is the key lever. It makes the CLI re-pull and upgrade **at launch,
  within the existing snapshot**, so a routine release lands without a snapshot
  rebuild. `/upgrade` runs the same script (its `--check`/`--enable` modes),
  so there is one implementation of the flag, not two.
- **Drift advisory.** Both also run the plugin's
  [`skills/upgrade/scripts/check_version_drift.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/upgrade/scripts/check_version_drift.py),
  which compares the installed version against the refreshed catalog and surfaces
  a "v{installed} → v{latest}; restart or run `/upgrade`" advisory. This advisory is the
  safety net for the one case the refresh cannot fix silently: a **restrictive
  network policy** that blocks the catalog/update fetch, or an update that applies
  only on the next launch. The script says nothing when the plugin is already current.
- **Manual escape hatch.** `/upgrade` updates on demand in any single session.

This setup does **not** do two things:

- **It does not touch your local machine.** Both scripts run only in cloud
  contexts. You paste the Setup script into the cloud UI. The SessionStart
  hook is gated on `DEV_TEAM_CLOUD_INSTALL=1` (unset locally by design). Neither
  script edits your local `~/.claude/settings.json`. To get the same auto-update
  behavior on your own machine, run the following once locally: `/upgrade` (consent to
  auto-update) or `python3 plugins/dev-team/skills/upgrade/scripts/enable_autoupdate.py --enable`.
- **It cannot outrun releases.** "Current" means the latest **released tag**
  (`marketplace.json`'s `source.ref`, which release-please bumps on merge). A
  missed release makes every session lag until someone cuts it. That is a release
  concern, not an install one.

## Caveats

- **Always `exit 0`.** A non-zero Setup script fails session startup. Guard every
  optional step with `|| true` and end with an explicit `exit 0`.
- **Time budget.** The Setup script has a few-minute budget. Keep installs
  best-effort and time-boxed. Do not block on anything that can hang.
- **Snapshot rebuild triggers.** Later sessions reuse the snapshotted Setup-script
  filesystem. Editing the Setup script (or other environment
  config) triggers a rebuild on the next session. That is how an updated script
  takes effect.
- **Network policy.** A restrictive outbound policy can block `marketplace add` /
  `install` (or `pip`/`apt`). When that happens, run skills from their files
  instead. See Option B in the companion doc.
- **Ephemeral VM.** The platform discards anything you do not commit and push when it reclaims the container.
- **`SessionStart` hook is fallback only.** `.claude/install-dev-team.sh` (gated
  by `DEV_TEAM_CLOUD_INSTALL=1`) installs the plugin too late for the current
  session. The plugin lands next session. Use the Setup script for same-session loading.
