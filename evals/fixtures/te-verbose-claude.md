# Project Instructions for AI Assistant

You are a highly skilled senior software engineer with deep expertise in TypeScript, React, and Node.js. You should act as an expert code reviewer and developer who pays close attention to detail and follows best practices at all times. Please note that these instructions are very important and should be followed carefully.

## About This Project

It's important to understand that this project is a customer relationship management (CRM) application built with modern web technologies. The application helps businesses manage their customer interactions, track sales pipelines, and generate reports. Remember to always keep this context in mind when making changes to the codebase.

This is a full-stack application that uses TypeScript on both the frontend and backend. The frontend is built with React and the backend uses Express.js with PostgreSQL as the database. We use Prisma as our ORM for database access.

## Technology Stack

You might want to familiarize yourself with the following technologies that are used in this project:

- **TypeScript 5.4**: We use TypeScript for type safety across the entire codebase. TypeScript helps us catch bugs at compile time and provides better developer experience with autocompletion and type checking. It's important to note that we use strict mode for TypeScript configuration.
  - We use strict null checks
  - We use no implicit any
  - We use strict function types
  - We prefer interfaces over type aliases for object shapes
    - Exception: union types should use type aliases
    - Exception: mapped types should use type aliases
      - But only when the mapping is complex
      - Simple mappings can use either
        - Use your best judgment here

- **React 18**: The frontend is built with React 18 using functional components and hooks. Please note that we do not use class components anywhere in the codebase. Consider using the following hooks:
  - `useState` for local component state
  - `useEffect` for side effects
  - `useMemo` for expensive computations
  - `useCallback` for stable function references
  - `useReducer` for complex state logic
  - `useContext` for theme and auth

- **Express.js 4**: Our backend API server uses Express.js. It's important to understand that we follow a layered architecture with controllers, services, and repositories.

- **PostgreSQL 15 with Prisma**: We use PostgreSQL as our primary database and Prisma as our ORM. Remember that all database queries should go through Prisma and we should never write raw SQL queries unless absolutely necessary.

## Project Structure

Perhaps it would be helpful to understand how the project is organized. The project follows a standard monorepo structure:

```
apps/
  web/           # React frontend application
    src/
      components/   # Reusable UI components
      pages/        # Page-level components
      hooks/        # Custom React hooks
      utils/        # Utility functions
      types/        # TypeScript type definitions
      services/     # API client services
      store/        # State management
  api/           # Express backend application
    src/
      controllers/  # Route handlers
      services/     # Business logic
      models/       # Prisma types
      middleware/   # Express middleware
      utils/        # Backend utilities
      routes/       # Route definitions
packages/
  shared/        # Shared types and utilities
  config/        # Shared configuration
  eslint-config/ # Shared ESLint configuration
```

## Code Style Guidelines

It's very important that you follow these code style guidelines when writing code for this project. Please pay careful attention to each of these rules:

### Naming Conventions

You should always use the following naming conventions throughout the codebase. These conventions are important for maintaining consistency:

- Components: Use PascalCase (e.g., `CustomerList`, `SalesPipeline`)
- Hooks: Use camelCase with `use` prefix (e.g., `useCustomer`, `useSalesData`)
- Utilities: Use camelCase (e.g., `formatCurrency`, `validateEmail`)
- Constants: Use SCREAMING_SNAKE_CASE (e.g., `MAX_RETRY_COUNT`, `API_BASE_URL`)
- Types/Interfaces: Use PascalCase (e.g., `Customer`, `SalesRecord`)
- Files: Use kebab-case for utility files, PascalCase for component files

Here are some examples of good naming:

```typescript
// Good component naming
function CustomerDetailCard({ customer }: CustomerDetailCardProps) {
  return <div>{customer.name}</div>;
}
```

```typescript
// Good hook naming
function useCustomerSearch(query: string) {
  const [results, setResults] = useState<Customer[]>([]);
  useEffect(() => {
    searchCustomers(query).then(setResults);
  }, [query]);
  return results;
}
```

```typescript
// Good utility naming
function formatCurrencyValue(amount: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(amount);
}
```

```typescript
// Good constant naming
const MAX_CUSTOMERS_PER_PAGE = 50;
const DEFAULT_SORT_ORDER = 'asc';
const API_TIMEOUT_MS = 5000;
```

```typescript
// Good interface naming
interface CustomerSearchFilters {
  query: string;
  status: CustomerStatus;
  dateRange: DateRange;
  sortBy: SortField;
}
```

### Error Handling

Remember to always handle errors properly. It's important to note that we use a Result type pattern for error handling in our services. Please note that you should never throw exceptions from service functions. Consider using the following pattern:

```typescript
// Good error handling pattern
async function createCustomer(
  input: CreateCustomerInput
): Promise<Result<Customer, AppError>> {
  const validation = validateCustomerInput(input);
  if (!validation.ok) {
    return err(new ValidationError(validation.error));
  }

  try {
    const customer = await db.customer.create({
      data: {
        name: validation.value.name,
        email: validation.value.email,
      },
    });
    return ok(customer);
  } catch (error) {
    return err(new DatabaseError('Failed to create customer', error));
  }
}
```

```typescript
// Good controller error handling
async function handleCreateCustomer(req: Request, res: Response) {
  const result = await customerService.create(req.body);
  if (!result.ok) {
    switch (result.error.type) {
      case 'validation':
        return res.status(400).json({ error: result.error.message });
      case 'conflict':
        return res.status(409).json({ error: result.error.message });
      default:
        return res.status(500).json({ error: 'Internal server error' });
    }
  }
  return res.status(201).json(result.value);
}
```

### Testing

It's very important that you write comprehensive tests for all code changes. Please note that we use Jest as our testing framework. You might want to consider the following testing guidelines:

- Write unit tests for all service functions
- Write integration tests for API endpoints
- Use descriptive test names that explain the behavior being tested
- Mock external dependencies using jest.spyOn
- Aim for at least 80% code coverage

Here is an example of a good test:

```typescript
describe('CustomerService.create', () => {
  it('should create a customer with valid input', async () => {
    const input = {
      name: 'John Doe',
      email: 'john@example.com',
    };

    const result = await service.create(input);

    expect(result.ok).toBe(true);
    expect(result.value).toMatchObject({
      name: 'John Doe',
      email: 'john@example.com',
    });
  });

  it('should return error for duplicate email', async () => {
    const input = {
      name: 'Jane Doe',
      email: 'existing@example.com',
    };

    const result = await service.create(input);

    expect(result.ok).toBe(false);
    expect(result.error.type).toBe('conflict');
  });
});
```

```typescript
describe('CustomerService.search', () => {
  it('should filter by status', async () => {
    const results = await service.search({
      status: 'active',
      limit: 10,
    });

    expect(results.ok).toBe(true);
    expect(results.value.every(c => c.status === 'active')).toBe(true);
  });
});
```

### API Design

You should follow RESTful conventions for all API endpoints. It's important to note that we use the following patterns:

- Use plural nouns for resource endpoints (e.g., `/customers`, `/sales`)
- Use HTTP methods correctly (GET for reads, POST for creates, PATCH for updates, DELETE for deletes)
- Return appropriate status codes
- Use pagination for list endpoints

## Database Guidelines

Please note that it's important to follow these database guidelines:

- Always use Prisma for database access. Never write raw SQL.
- Use database transactions for operations that modify multiple tables.
- Add indexes for frequently queried columns and foreign keys.
- Use soft deletes for customer data (add `deletedAt` column).
- Always include `createdAt` and `updatedAt` timestamps.

## Deployment

Remember that our deployment process involves the following steps. It's important to understand this process:

1. Run `npm run lint` to check for linting errors
2. Run `npm test` to run all tests
3. Run `npm run build` to build the project
4. Run `npm run migrate:deploy` to apply database migrations
5. Deploy to staging first, then production

## Common Commands

You might want to use the following commands when working with this project:

- `npm run dev` — Start the development server. This will start both the frontend and backend in development mode with hot reloading enabled.
- `npm test` — Run the test suite. This will run all unit tests and integration tests using Jest.
- `npm run test:watch` — Run tests in watch mode. This is useful during development.
- `npm run lint` — Run ESLint to check for code style issues. This uses our shared ESLint configuration.
- `npm run lint:fix` — Run ESLint with auto-fix. This will automatically fix any fixable issues.
- `npm run build` — Build the project for production. This compiles TypeScript and bundles the frontend.
- `npm run typecheck` — Run TypeScript type checking without emitting files.
- `npm run prisma:migrate` — Run Prisma migrations in development mode.
- `npm run prisma:generate` — Regenerate Prisma client after schema changes.
- `npm run prisma:studio` — Open Prisma Studio for database browsing.

## Additional Notes

It's important to remember that this project is actively maintained and we follow semantic versioning. Please note that all pull requests should include appropriate tests and documentation updates. You might want to consider running the full test suite before submitting your changes. Remember to keep your branch up to date with the main branch.
