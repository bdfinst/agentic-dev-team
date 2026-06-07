# Giving CI read access to the telemetry repo

To make the cost-regression gate (#171) — and any future rollup-based gate —
enforce against **real** data, CI needs to **read** the private `agent-telemetry`
repo and build the cross-machine rollup. This doc sets that up with least
privilege: **read-only, single-repo, revocable**, and with no write access to
your data.

Companion docs: [`telemetry-repo-security.md`](telemetry-repo-security.md) (how
machines *write* digests) and the watermark/sync flow in `/session-review`.

## Principle

- CI only ever **reads** the digest database — it never writes telemetry.
- The credential is scoped to the **one** `agent-telemetry` repo, **read-only**,
  and can be revoked without touching anything else.
- The raw `~/.claude/projects` transcripts are never involved; CI consumes the
  already-sanitized, metrics-only digest.

## Recommended: a read-only deploy key

A deploy key authorizes an SSH key for a **single repository**. Make it
**read-only** so CI can clone but never push.

### 1. Generate a dedicated keypair (locally)

```bash
ssh-keygen -t ed25519 -f ./telemetry-ci -N "" -C "agentic-dev-team CI read-only"
# produces:  telemetry-ci  (private)   telemetry-ci.pub  (public)
```

### 2. Add the PUBLIC key to `agent-telemetry` as a read-only deploy key

GitHub → `agent-telemetry` → Settings → Deploy keys → **Add deploy key**:

- Title: `agentic-dev-team CI (read-only)`
- Key: contents of `telemetry-ci.pub`
- **Leave "Allow write access" UNCHECKED** ← this is what keeps CI read-only.

### 3. Add the PRIVATE key to `agentic-dev-team` as an Actions secret

GitHub → `agentic-dev-team` → Settings → Secrets and variables → Actions →
**New repository secret**:

- Name: `TELEMETRY_DEPLOY_KEY`
- Value: contents of `telemetry-ci` (the private key)

Then delete the local key files (`rm telemetry-ci telemetry-ci.pub`) — GitHub now
holds both halves where they belong.

### 4. Consume it in the workflow

This wiring is **already in place** — see the `cost-regression` job in
[`.github/workflows/plugin-tests.yml`](../../../.github/workflows/plugin-tests.yml).
The job loads the key, clones the data repo read-only, builds a per-session cost
series from the digests, and runs the regression check against it. The
credential steps are gated so fork PRs (which have no secret access) skip them
and fall back to the blocking self-test:

```yaml
  cost-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Install python3 + jq
        run: sudo apt-get update && sudo apt-get install -y jq python3
      # Secrets are NOT exposed to forked-PR runs (see caveat) — gate on that:
      - name: Load telemetry deploy key (read-only)
        if: ${{ github.event_name != 'pull_request' || github.event.pull_request.head.repo.fork == false }}
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.TELEMETRY_DEPLOY_KEY }}
      - name: Clone telemetry (read-only) and build the cross-machine cost baseline
        if: ${{ github.event_name != 'pull_request' || github.event.pull_request.head.repo.fork == false }}
        run: |
          git clone --depth 1 git@github.com:bdfinst/agent-telemetry.git /tmp/telemetry
          python3 scripts/session_extract.py --cost-log /tmp/telemetry/digests \
            -o /tmp/telemetry-cost-log.jsonl
          echo "COST_BASELINE_LOG=/tmp/telemetry-cost-log.jsonl" >> "$GITHUB_ENV"
      - name: Run cost-regression check
        run: bash scripts/cost-regression-check.sh
```

> Why `--cost-log` and not `--rollup`? The regression meter
> (`cost_meter.py regression`) compares the **latest** session against the
> rolling mean of priors, so it needs a *time-ordered per-session series*, not a
> single aggregate. `session_extract.py --cost-log <digests>` emits exactly that
> (`{"total":{"cost_usd":..}}` records, oldest→newest, deduped on `session_id`).
> The real cross-machine check is **warn-only** — a non-deterministic meter must
> not hard-fail an unrelated code PR.

## Alternative: a fine-grained PAT (read-only)

If you prefer HTTPS: create a **fine-grained** PAT scoped to **only**
`agent-telemetry` with **Contents: Read-only**, store it as the
`TELEMETRY_DEPLOY_KEY` (or `TELEMETRY_TOKEN`) secret, and clone via
`https://x-access-token:${TOKEN}@github.com/bdfinst/agent-telemetry.git`. Prefer
the deploy key — it is the tightest scope (one repo, read-only) and needs no
account-level token.

## Security notes and caveats

- **Read-only, by construction.** The deploy key has no write access, so a leak
  exposes *read* of one private metrics repo — never write, never your account.
- **Fork-PR caveat (important).** GitHub does not expose secrets to workflows
  triggered by pull requests from forks. So the cost gate runs on branches in
  this repo and on internal PRs, but **not** on fork PRs — those fall back to the
  mechanism self-test. For a solo/private setup this is a non-issue; documented so
  the coverage boundary is honest.
- **Rotation.** To rotate: generate a new key, add it, update the secret, delete
  the old deploy key. To revoke entirely: delete the deploy key on
  `agent-telemetry` — CI loses read access immediately, nothing else affected.
- **Never echo the key** in workflow logs; `ssh-agent` keeps it out of the
  environment dump.

## What this unblocks

- **#171** — the cost-regression gate compares each run against the real
  cross-machine baseline instead of only self-testing the mechanism.
- Any future gate that wants cross-machine rollup data in CI (the same clone +
  `--rollup` pattern).
