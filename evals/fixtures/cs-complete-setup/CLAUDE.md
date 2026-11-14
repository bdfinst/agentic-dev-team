# Acme Dashboard

A React + TypeScript internal dashboard for managing customer accounts.

## Architecture

- **Frontend**: React 18 with TypeScript, Vite bundler
- **State**: React Query for server state
- **Backend**: Express API in `server/`, PostgreSQL via Prisma ORM
- **Auth**: JWT bearer-token auth, middleware in `server/middleware/auth.ts`

## Directory Structure

- `src/` — React frontend source (entry: `src/main.tsx`)
  - `src/components/` — Shared UI components
  - `src/features/` — Feature modules (accounts)
  - `src/hooks/` — Custom React hooks
  - `src/utils/` — Helper functions
- `server/` — Express backend
  - `server/routes/` — API route handlers
  - `server/middleware/` — Express middleware (JWT auth)
  - `server/prisma/` — Prisma schema

## Commands

- `npm run dev` — Start frontend dev server (port 3000)
- `npm run server` — Start backend dev server (port 4000)
- `npm test` — Run Vitest unit tests
- `npm run lint` — ESLint + Prettier check
- `npm run db:migrate` — Run Prisma migrations
- `npm run build` — Production build: frontend to `dist/`, server bundle to `dist/server/index.js`

## Coding Conventions

- Use functional components with hooks; no class components
- Colocate tests next to source files as `*.test.ts(x)`
- All API responses follow `{ data, error, meta }` envelope
- Use `zod` for runtime validation of API inputs
- Prefer named exports over default exports (tool config files excepted)
- Extract hooks for complex component logic (function length limit: `.claude/rules/style.md`)
