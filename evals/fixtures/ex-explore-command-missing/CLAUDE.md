# Probe Service

A small HTTP service for managing orders, with a dev-team-style command registry.

## Architecture

- **Runtime**: Node.js + Express
- **Storage**: PostgreSQL via Prisma
- **Tests**: Vitest (unit) + Playwright (e2e)

## Directory Structure

- `src/` — service source
  - `src/routes/` — HTTP route handlers
  - `src/db/` — Prisma client and queries
- `commands/` — slash command definitions
- `tests/` — test suites

## Commands

- `npm run dev` — start the dev server (port 4000)
- `npm test` — run Vitest unit tests
- `npm run test:e2e` — run Playwright end-to-end tests

## Slash Commands Registry

| Command | File | What It Does |
|---------|------|--------------|
| `/explore` | `commands/explore.md` | Charter-driven exploratory testing of a running endpoint |
