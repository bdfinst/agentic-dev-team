# Invoice Generator

A Node.js service that generates PDF invoices from order data.

## Architecture

- `src/api/` — REST API routes for invoice CRUD operations
- `src/templates/` — Handlebars templates for invoice layouts
- `src/services/pdf.ts` — PDF generation using Puppeteer
- `src/queue/` — Bull queue workers for async PDF generation

## Directory Layout

- `src/api/routes.ts` — Route definitions
- `src/api/controllers/` — Request handlers
- `src/models/` — Mongoose schemas
- `lib/validators/` — Input validation helpers

## Commands

- `npm run dev` — Start development server with hot reload
- `npm run deploy` — Deploy to production via CI pipeline
- `npm run generate:types` — Generate TypeScript types from schemas
- `npm test` — Run Jest test suite

## Configuration

- Environment variables are defined in `.env.example`
- Security rules are documented in `.claude/rules/security.md`

## Coding Conventions

- Use async/await for all asynchronous operations
- Validate all inputs at the controller level with Joi
- Log structured JSON using the `pino` logger
