// ---- domain/money.ts ----

// The ledger runs in one currency, so Money carries cents only
export class Money {
  private constructor(readonly cents: number) {}

  static ofCents(cents: number): Money {
    if (!Number.isInteger(cents) || cents < 0) {
      throw new RangeError("cents must be a non-negative integer");
    }
    return new Money(cents);
  }

  subtract(other: Money): Money {
    return Money.ofCents(this.cents - other.cents);
  }

  isGreaterThan(other: Money): boolean {
    return this.cents > other.cents;
  }
}

// ---- domain/customer.ts ----

export class Customer {
  private constructor(
    readonly customerId: string,
    private limit: Money,
    private readonly limitCeiling: Money,
  ) {}

  static create(
    customerId: string,
    withdrawalLimit: Money,
    limitCeiling: Money,
  ): Customer {
    Customer.assertWithinCeiling(withdrawalLimit, limitCeiling);
    return new Customer(customerId, withdrawalLimit, limitCeiling);
  }

  get withdrawalLimit(): Money {
    return this.limit;
  }

  changeWithdrawalLimit(newLimit: Money): void {
    Customer.assertWithinCeiling(newLimit, this.limitCeiling);
    this.limit = newLimit;
  }

  private static assertWithinCeiling(limit: Money, ceiling: Money): void {
    if (limit.isGreaterThan(ceiling)) {
      throw new Error("withdrawal limit cannot exceed the customer's ceiling");
    }
  }
}

// ---- domain/account.ts ----

export class Account {
  constructor(
    readonly accountId: string,
    readonly ownerId: string,
    private balance: Money,
  ) {}

  get availableBalance(): Money {
    return this.balance;
  }

  withdraw(amount: Money): void {
    if (amount.isGreaterThan(this.balance)) {
      throw new Error("insufficient funds");
    }
    this.balance = this.balance.subtract(amount);
  }
}

// ---- domain/withdrawal-policy.ts ----

export class WithdrawalPolicy {
  assertPermitted(owner: Customer, account: Account, amount: Money): void {
    if (account.ownerId !== owner.customerId) {
      throw new Error("customer does not own the account");
    }
    if (amount.isGreaterThan(owner.withdrawalLimit)) {
      throw new Error("amount exceeds the customer's withdrawal limit");
    }
  }
}

// ---- application/withdraw-funds.ts ----

export interface CustomerRepository {
  findById(customerId: string): Promise<Customer | null>;
}

export interface AccountRepository {
  findById(accountId: string): Promise<Account | null>;
  save(account: Account): Promise<void>;
}

export class WithdrawFunds {
  constructor(
    private readonly customers: CustomerRepository,
    private readonly accounts: AccountRepository,
    private readonly policy: WithdrawalPolicy,
  ) {}

  async execute(
    customerId: string,
    accountId: string,
    amount: Money,
  ): Promise<void> {
    const owner = await this.customers.findById(customerId);
    const account = await this.accounts.findById(accountId);
    if (!owner || !account) {
      throw new Error("customer or account not found");
    }
    this.policy.assertPermitted(owner, account, amount);
    account.withdraw(amount);
    await this.accounts.save(account);
  }
}
