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
- `production`: deploy with `fly.production.toml`, only after staging is healthy

Refuse any other argument.

## Prerequisites

The `fly` CLI is installed and logged in (`fly auth whoami` succeeds).

## Steps

Stop and report the failing command if any step exits non-zero.

1. Run the `test` skill.
2. For `production` only: run `fly status --config fly.staging.toml` and stop unless every staging machine reports its health check as passing.
3. Run `fly deploy --config fly.<environment>.toml`. Fly builds the image from `Dockerfile`, waits for the `/health` check on each new machine, and keeps the previous release running if a check fails.
4. Report the environment, the released version from `fly releases --config fly.<environment>.toml`, and the deploy result.
