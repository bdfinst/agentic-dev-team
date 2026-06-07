# Telemetry repository — security & setup

The cross-machine telemetry repo (Delta D, #178) is a **private append-only
database**, not a code repo. This doc explains how to wire it up so machines can
write to it directly — **no pull-request toil for data** — while keeping access
least-privilege and revocable.

## The model: treat the repo like a database

- **One writer-owned file per machine:** `digests/<host>/session-digest.jsonl`.
  Because no two machines touch the same file, concurrent writes never conflict —
  the same property a per-shard append log gives a database.
- **Direct writes to the default branch.** Each machine does
  `extract → commit → pull --rebase → push`. There is **no PR**, because review
  adds toil with no security value over append-only, non-executable metric rows.
- **Producer-enforced privacy.** The extractor emits metrics only — counts,
  ratios, token numbers, model ids, and a project **basename** (never a path,
  prompt, command, or code). The repo is a sink for already-sanitized data.

## Repository settings

Configure the data repo (e.g. `agent-telemetry`) like this:

| Setting | Value | Why |
|---|---|---|
| Visibility | **Private** | It holds your usage metrics; never make it public. |
| Branch protection on default branch | **Off** (no "Require a pull request before merging", no required reviews, no required status checks) | Machines push data directly; a PR gate would block every sync. |
| Push access | **Only you / your machines** (see deploy keys below) | Least privilege. |
| Contents | **Metrics JSONL only** | No code runs from here; keep it that way. |

There is intentionally **no CI and no merge queue** on this repo — it is data, so
the dev-team quality gates (which guard *code*) do not apply.

## Authentication — least privilege, per machine

Do **not** point this at your account-wide SSH key or a classic personal access
token with `repo` scope: either would grant every machine access to *all* your
repositories. Use one of these, scoped to **this repo only**:

### Option A — per-host deploy key (recommended)

A deploy key is an SSH key authorized for a **single repository**, so a machine
that can write telemetry cannot touch anything else.

```bash
# On each machine:
ssh-keygen -t ed25519 -f ~/.ssh/agent-telemetry -N "" -C "telemetry-$(hostname -s)"
cat ~/.ssh/agent-telemetry.pub
# GitHub → agent-telemetry repo → Settings → Deploy keys → Add deploy key
#   - paste the public key
#   - CHECK "Allow write access"
```

Point git at that key for this repo (so it isn't used for anything else):

```bash
# ~/.ssh/config
Host agent-telemetry.github.com
  HostName github.com
  IdentityFile ~/.ssh/agent-telemetry
  IdentitiesOnly yes
```

…and set the remote to that host alias:
`git@agent-telemetry.github.com:<owner>/agent-telemetry.git`.

**Revocation:** lose a laptop → delete that one deploy key. Other machines are
unaffected, and nothing else of yours was ever exposed.

### Option B — fine-grained personal access token

If you prefer HTTPS: create a **fine-grained** PAT scoped to **only** the
`agent-telemetry` repository with **Repository permissions → Contents: Read and
write** and nothing else. Store it in a credential helper (macOS Keychain, git
credential manager) — never in plaintext or in the repo. Prefer one token per
machine so tokens are individually revocable.

> Avoid classic PATs and broad SSH keys. The whole point is that a compromised
> telemetry credential leaks *metrics for one repo*, not your code or account.

## Configure dev-team to use it

Tell the plugin where the repo is (the `/session-review` skill will prompt and
write this for you on first run):

```bash
# Env var (highest precedence):
export DEV_TEAM_TELEMETRY_REMOTE="git@agent-telemetry.github.com:<owner>/agent-telemetry.git"

# …or the config file ~/.claude/.dev-team/telemetry.json:
{ "remote": "git@agent-telemetry.github.com:<owner>/agent-telemetry.git" }
```

Optional keys / env vars: `clone` / `DEV_TEAM_TELEMETRY_CLONE` (local working
clone, default `~/.claude/.dev-team/agent-telemetry`) and `host` /
`DEV_TEAM_TELEMETRY_HOST` (label, default `hostname -s`).

Then sync:

```bash
scripts/telemetry-sync.sh --check   # validate config (no network)
scripts/telemetry-sync.sh           # extract -> commit -> pull --rebase -> push
```

## What is and isn't protected

- **Protected by design:** access is per-repo and per-machine (revocable); writes
  are conflict-free; the repo is private; only sanitized metrics ever leave a
  machine; raw `~/.claude/projects/**` transcripts never leave.
- **Your responsibility:** keep the repo private, keep deploy keys/tokens scoped
  and rotated, and don't add collaborators who shouldn't see your usage metrics.

## Why no PR gate is the right call here

PRs exist to review *changes to code that will execute*. This repo stores
append-only, non-executable metric rows in per-host files. A PR per sync would be
pure toil — it cannot catch a "bug" (there is no logic), and the privacy boundary
is enforced upstream by the extractor, not by a reviewer. So: gate the **code**
that produces the data (the dev-team repo's CI does), and let the **data** flow
directly into its database.
