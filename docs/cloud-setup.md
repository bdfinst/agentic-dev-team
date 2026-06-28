# Cloud setup: loading the dev-team plugin into a web session

This is the focused recipe for making the `dev-team@bfinster` plugin work in a
**Claude Code on the web** session (claude.ai/code) — in the **same** session,
not the next one. For the broader walkthrough (including the file-based
fallback), see
[`using-plugin-skills-in-the-web-environment.md`](using-plugin-skills-in-the-web-environment.md).

## Why declaring the plugin isn't enough

Claude loads every skill, agent, and slash command **once, when it starts.**
A plugin is only visible if its files are on disk *before* that happens.
So "install the plugin" really means "get the plugin on disk before Claude starts."

That timing is the whole story:

| Mechanism | Runs… | Plugin loads… |
|---|---|---|
| **Setup script** (cloud UI) | **before** Claude boots; filesystem snapshotted & reused | **this** session ✅ |
| **`SessionStart` hook** (`.claude/install-dev-team.sh`) | **after** Claude boots | **next** session only ⚠️ |

The Setup script is the supported way to install software before the session
starts (you cannot replace the underlying machine image). The `SessionStart`
hook runs too late — the plugin it installs only takes effect in the *next*
session — so use the Setup script as your primary path and the hook as a fallback.

The `claude` CLI **is** available in cloud environments, so the install commands
below run fine from the Setup script.

## The snippet to paste into the Setup script field

claude.ai/code → Environment → **Setup script**. The script below checks whether
the plugin is already installed and always exits without error (a non-zero exit
**fails** session startup). It uses a repo-committed bootstrap when one exists,
and otherwise installs the plugin directly:

```bash
#!/bin/bash
set -uo pipefail
MARKETPLACE_REPO="bdfinst/agentic-dev-team"
PLUGIN="dev-team@bfinster"
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BOOTSTRAP="$ROOT/.claude/scripts/dev-team-bootstrap.sh"
if [ -f "$BOOTSTRAP" ]; then
  bash "$BOOTSTRAP" || echo "[setup] bootstrap reported issues — continuing."
  exit 0
fi
echo "[setup] no $BOOTSTRAP — installing dev-team inline for this session."
if command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add "$MARKETPLACE_REPO" >/dev/null 2>&1 || true
  claude plugin install "$PLUGIN" >/dev/null 2>&1 || true
fi
exit 0
```

If you also want this repo's test/gate toolchain (`jq`, `shellcheck`, `bats`,
the Python dev deps, `gh`) in the same step, paste the body of
[`.claude/cloud-setup.sh`](../.claude/cloud-setup.sh) instead — it installs the
toolchain *and* the plugin, and follows the same exit-0 discipline. It also
installs Node 24+ and runs `npm ci`, which sets up the git hooks
(`pre-commit`, `pre-push`, `commit-msg`) so commits and pushes in the cloud
session run the same checks you'd run locally. (Skip this only if you don't
intend to commit from the session — it adds a minute to setup.)

## Verify it worked

Run the headless probe in the session. It boots a fresh Claude, lists every
available skill, and counts the `dev-team:*` ones:

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

## Caveats

- **Always `exit 0`.** A non-zero Setup script fails session startup. Guard every
  optional step with `|| true` and end with an explicit `exit 0`.
- **Time budget.** The Setup script has a few-minute budget. Keep installs
  best-effort and time-boxed; don't block on anything that can hang.
- **Snapshot rebuild triggers.** The Setup-script filesystem is snapshotted and
  reused by later sessions. Editing the Setup script (or other environment
  config) triggers a rebuild on the next session — that's how an updated script
  takes effect.
- **Network policy.** A restrictive outbound policy can block `marketplace add` /
  `install` (or `pip`/`apt`). When that happens, run skills from their files
  instead — see Option B in the companion doc.
- **Ephemeral VM.** Anything not committed and pushed is lost when the container
  is reclaimed.
- **`SessionStart` hook is fallback only.** `.claude/install-dev-team.sh` (gated
  by `DEV_TEAM_CLOUD_INSTALL=1`) installs the plugin too late for the current
  session; it lands next session. Use the Setup script for same-session loading.
