---
name: deploy
description: Deploy the application to staging or production on Fly.io.
argument-hint: "[staging | production]"
user-invocable: true
disable-model-invocation: true
---

# Deploy

## Parse Arguments

Arguments: $ARGUMENTS

- `staging` (default): deploy with `fly.staging.toml`
- `production`: deploy to staging first, then promote the same image with `fly.production.toml`

Refuse any other argument.

## Prerequisites

The `fly` CLI is installed and logged in (`fly auth whoami` succeeds).

## Steps

Stop and report the failing command if any step exits non-zero.

1. Run the `test` skill.
2. Run `fly deploy --config fly.staging.toml`. Fly builds the image from `Dockerfile` (which runs `npm run build`), waits for the `/health` check on each new machine, and keeps the previous release running if a check fails.
3. For `production` only: promote the image staging just verified. Read it with `fly image show --config fly.staging.toml`, then run `fly deploy --config fly.production.toml --image <that image>`.
4. Report the environment, the released version from `fly releases --config fly.<environment>.toml`, and the deploy result.
