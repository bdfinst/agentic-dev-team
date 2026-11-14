# Parcel Tracker

An Express API that records shipments and polls carrier APIs for tracking updates.

## Architecture

- **Runtime**: Node.js 20, TypeScript, Express 4; entry point `src/server.ts`
- **Routes**: HTTP handlers in `src/routes/`
- **Carriers**: one adapter per carrier API in `src/carriers/`
- **Database**: PostgreSQL; SQL migrations in `src/db/migrations/`, applied by `scripts/migrate.sh`
- **Tests**: Vitest suites in `tests/`

## Directory Structure

- `src/server.ts` — app setup and route mounting
- `src/routes/shipments.ts` — shipment create/read routes
- `src/carriers/ups.ts` — UPS tracking adapter
- `src/db/migrations/` — ordered SQL migrations
- `scripts/` — shell helpers used by npm scripts and agents
- `tests/` — Vitest suites
- `.claude/rules/` — project rules for Claude
- `.claude/skills/release/` — release workflow skill
- `.claude/agents/` — project subagents

## Commands

- `npm run dev` — start the API with reload (port 4100)
- `npm test` — run Vitest once
- `npm run lint` — ESLint over `src/` and `tests/`
- `npm run build` — compile TypeScript to `dist/`
- `npm run db:migrate` — apply pending migrations

## Coding Conventions

- Return `{ data, error }` from every route handler.
- Validate request bodies with `zod` schemas next to the route.
- Carrier adapters never throw; they return a `TrackingResult`.
- Test rules live in `.claude/rules/testing.md`.
