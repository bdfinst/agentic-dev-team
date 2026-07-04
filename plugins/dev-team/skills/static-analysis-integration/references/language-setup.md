# Per-language static-analysis setup

User-facing configuration guide for the static-analysis integration: the
build-time self-heal pass that runs at `/build`'s review checkpoints and the
`/code-review` static pre-pass. One section per registered lane, below. This
guide is the single source of truth for the manual setup commands; the
registry of what runs (and how) lives in [`tool-configs.md`](tool-configs.md)
§ Build-time lanes.

## Opting out

Set `DEV_TEAM_STATIC_SELF_HEAL=off` to skip the entire build-time static
self-heal pass — no tool probe or invocation occurs, one info line notes the
skip, and review checkpoints proceed straight to semantic review. Any other
value (or unset) leaves the pass enabled. This mirrors the
`DEV_TEAM_REVIEW_VALUE=off` convention and does not affect `/code-review`'s
full-repo static pre-pass.

## Per-lane section contract

Each language section below is added by the issue that registers its lane
and covers, in order:

1. **Tools and roles** — which tools the lane uses and what each does
   (autofix-capable vs diagnostic-only).
2. **Repo-level install** — how to install them as project-local,
   versioned-with-the-repo dependencies, never user-level/global, so the
   toolchain is reproducible for every contributor and CI.
3. **Configuration** — which config files the tools honor.
4. **Verification** — the lane's detection probe commands, to confirm the
   setup is detected.
5. **Opt-out** — the `DEV_TEAM_STATIC_SELF_HEAL=off` toggle above.
6. **Recognized equivalent providers** — the slot's ordered provider list
   and each provider's qualification status.

Each section also carries a one-line pointer to `/project-init` as the
one-command path to the same repo-level install; this guide remains the
source of truth for the manual commands.

## Python

No lane registered — section added by #807.

## JS/TS

No lane registered — section added by #808.

## C#

No lane registered — section added by #809.

## Java

No lane registered — section added by #810.
