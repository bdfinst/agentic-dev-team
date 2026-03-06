# Acme Dashboard

A React + TypeScript internal dashboard for managing customer accounts, billing, and support tickets.

## Architecture

- **Frontend**: React 18 with TypeScript, Vite bundler
- **State**: Zustand for global state, React Query for server state
- **Backend**: Express API in `server/`, PostgreSQL via Prisma ORM
- **Auth**: JWT-based auth with refresh tokens, middleware in `server/middleware/auth.ts`

## Directory Structure

- `src/` — React frontend source
  - `src/components/` — Shared UI components
  - `src/features/` — Feature modules (accounts, billing, tickets)
  - `src/hooks/` — Custom React hooks
  - `src/utils/` — Helper functions
- `server/` — Express backend
  - `server/routes/` — API route handlers
  - `server/middleware/` — Auth, logging, error handling
  - `server/prisma/` — Schema and migrations

## Commands

- `npm run dev` — Start frontend dev server (port 3000)
- `npm run server` — Start backend dev server (port 4000)
- `npm test` — Run Vitest unit tests
- `npm run test:e2e` — Run Playwright end-to-end tests
- `npm run lint` — ESLint + Prettier check
- `npm run db:migrate` — Run Prisma migrations
- `npm run build` — Production build

## Coding Conventions

- Use functional components with hooks; no class components
- Colocate tests next to source files as `*.test.ts(x)`
- All API responses follow `{ data, error, meta }` envelope
- Use `zod` for runtime validation of API inputs
- Prefer named exports over default exports
- Keep components under 150 lines; extract hooks for complex logic
