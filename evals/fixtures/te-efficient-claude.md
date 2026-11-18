# myapp — Task Management API

## Stack

- Node.js 20, TypeScript 5.4, Express 4
- PostgreSQL 15, Prisma ORM
- Jest for testing, ESLint + Prettier

## Commands

- Run scripts from `package.json`.
- Migrate the database with `npx prisma migrate dev`.

## Code Style

- Return `Result<T, AppError>` from services. Never throw from services.
- Prefer `readonly` arrays and `Readonly<T>` for shared data.
- Name handlers `handleVerbNoun` (e.g., `handleCreateTask`).
- Name validators `validateNoun` (e.g., `validateTask`).
- Export one symbol per file in services and controllers.

## File Layout

| Directory | Contents |
| --------- | -------- |
| `src/controllers/` | Express route handlers |
| `src/services/` | Business logic |
| `src/models/` | Prisma schema types |
| `src/middleware/` | Auth, validation, error handling |
| `src/utils/` | Pure helper functions |

## Testing

- Place tests in `__tests__/` adjacent to source.
- Name test files `*.test.ts`.
- Use `describe` per function, `it` per behavior.
- Mock external services with `jest.spyOn`.

## Error Handling

| Layer | Strategy |
| ----- | -------- |
| Controller | Catch `Result.err`, return HTTP status |
| Middleware | Global error handler logs + 500 |

## Database

- Query only through Prisma. Do not write raw SQL.
- Use transactions for multi-table writes.
- Index foreign keys and frequently filtered columns.
