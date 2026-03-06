# myapp — Task Management API

## Stack

- Node.js 20, TypeScript 5.4, Express 4
- PostgreSQL 15, Prisma ORM
- Jest for testing, ESLint + Prettier

## Commands

| Action | Command |
| ------ | ------- |
| Dev server | `npm run dev` |
| Test | `npm test` |
| Lint | `npm run lint` |
| Build | `npm run build` |
| Migrate | `npx prisma migrate dev` |

## Code Style

- Use `Result<T, E>` for all service returns. Never throw from services.
- Prefer `readonly` arrays and `Readonly<T>` for shared data.
- Name handlers `handleVerbNoun` (e.g., `handleCreateTask`).
- Name validators `validateNoun` (e.g., `validateTask`).
- One export per file for services and controllers.

## File Layout

| Directory | Contents |
| --------- | -------- |
| `src/controllers/` | Express route handlers |
| `src/services/` | Business logic, returns `Result` |
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
| Service | Return `Result.err(AppError)` |
| Middleware | Global error handler logs + 500 |

## Database

- All queries go through Prisma. No raw SQL.
- Use transactions for multi-table writes.
- Index foreign keys and frequently filtered columns.
