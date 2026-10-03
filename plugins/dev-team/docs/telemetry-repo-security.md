# Telemetry repository — security & setup

The cross-machine telemetry repo (Delta D, #178) is a **private append-only
database**, not a code repo. This doc explains how to wire it up so machines can
write to it directly, with **no pull-request toil for data**. Access stays
least-privilege and revocable.

## The model: treat the repo like a database

- **One writer-owned file per machine:** `digests/<host>/session-digest.jsonl`.
  Because no two machines touch the same file, concurrent writes never conflict.
  A per-shard append log gives a database the same property.
- **Direct writes to the default branch.** Each machine does
  `extract → commit → pull --rebase → push`. There is **no PR**. Review
  adds toil and no security value over append-only, non-executable metric rows.
- **Producer-enforced privacy.** The extractor emits metrics only: counts,
  ratios, token numbers, model ids, and a project **basename** (never a path,
  prompt, command, or code). The repo is a sink for already-sanitized data.

## Repository settings

Configure the data repo (for example, `agent-telemetry`) like this:

| Setting | Value | Why |
|---|---|---|
| Visibility | **Private** | It holds your usage metrics; never make it public. |
| Branch protection on default branch | **Off** (no "Require a pull request before merging", no required reviews, no required status checks) | Machines push data directly; a PR gate would block every sync. |
| Push access | **Only you / your machines** (see deploy keys below) | Least privilege. |
| Contents | **Metrics JSONL only** | No code runs from here; keep it that way. |

There is intentionally **no CI and no merge queue** on this repo. It holds data, so
the dev-team quality gates (which guard *code*) do not apply.

## Authentication — least privilege, per machine

Do **not** point this at your account-wide SSH key or a classic personal access
token with `repo` scope. Either would grant every machine access to *all* your
repositories. Use one of these options, scoped to **this repo only**:

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

Point git at that key for this repo, so git does not use the key for anything else:

```bash
# ~/.ssh/config
Host agent-telemetry.github.com
  HostName github.com
  IdentityFile ~/.ssh/agent-telemetry
  IdentitiesOnly yes
```

…and set the remote to that host alias:
`git@agent-telemetry.github.com:<owner>/agent-telemetry.git`.

**Revocation:** if you lose a laptop, delete that one deploy key. Other machines are
unaffected, and nothing else of yours was ever exposed.

### Option B — fine-grained personal access token

If you prefer HTTPS, create a **fine-grained** PAT scoped to **only** the
`agent-telemetry` repository. Grant **Repository permissions → Contents: Read and
write** and nothing else. Store the token in a credential helper (macOS Keychain, git
credential manager), never in plaintext or in the repo. Prefer one token per
machine so you can revoke tokens individually.

> Avoid classic PATs and broad SSH keys. A compromised
> telemetry credential must leak *metrics for one repo*, not your code or account.

## Configure dev-team to use it

Tell the plugin where the repo is. The `/session-review` skill prompts for this and
writes it for you on first run:

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

- **Protected by design:** access is per-repo and per-machine (revocable).
- **Protected by design:** writes are conflict-free, and the repo is private.
- **Protected by design:** only sanitized metrics leave a
  machine. Raw `~/.claude/projects/**` transcripts never leave.
- **Your responsibility:** keep the repo private.
- **Your responsibility:** keep deploy keys and tokens scoped
  and rotated.
- **Your responsibility:** do not add collaborators who should not see your usage metrics.

## Why no PR gate is the right call here

PRs exist to review *changes to code that will execute*. This repo stores
append-only, non-executable metric rows in per-host files. A PR per sync is
pure toil. It cannot catch a "bug" because there is no logic. The extractor enforces the privacy boundary
upstream, not a reviewer. So gate the **code**
that produces the data (the dev-team repo's CI does), and let the **data** flow
directly into its database.
