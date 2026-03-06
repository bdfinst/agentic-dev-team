// PASS: Well-separated concerns, single responsibility, dependency injection

interface Logger {
  info(msg: string): void;
  error(msg: string, err?: Error): void;
}

interface UserRepository {
  findById(id: string): Promise<User | null>;
  save(user: User): Promise<void>;
}

interface User {
  id: string;
  name: string;
  email: string;
  active: boolean;
}

class UserService {
  constructor(
    private readonly repo: UserRepository,
    private readonly logger: Logger,
  ) {}

  async activate(userId: string): Promise<void> {
    const user = await this.repo.findById(userId);
    if (!user) {
      this.logger.error(`User not found: ${userId}`);
      throw new Error("User not found");
    }
    await this.repo.save({ ...user, active: true });
    this.logger.info(`Activated user ${userId}`);
  }
}

class UserValidator {
  validate(input: Partial<User>): string[] {
    const errors: string[] = [];
    if (!input.name || input.name.length < 2) {
      errors.push("Name must be at least 2 characters");
    }
    if (!input.email || !input.email.includes("@")) {
      errors.push("Valid email is required");
    }
    return errors;
  }
}

export { UserService, UserValidator };
export type { User, UserRepository, Logger };
