// ---- domain/money.ts ----

export class Money {
  private constructor(
    readonly amountCents: number,
    readonly currency: string,
  ) {}

  static ofCents(amountCents: number, currency: string): Money {
    if (!Number.isInteger(amountCents) || amountCents < 0) {
      throw new RangeError("amountCents must be a non-negative integer");
    }
    return new Money(amountCents, currency);
  }

  add(other: Money): Money {
    this.assertSameCurrency(other);
    return Money.ofCents(this.amountCents + other.amountCents, this.currency);
  }

  subtract(other: Money): Money {
    this.assertSameCurrency(other);
    return Money.ofCents(this.amountCents - other.amountCents, this.currency);
  }

  isGreaterThan(other: Money): boolean {
    this.assertSameCurrency(other);
    return this.amountCents > other.amountCents;
  }

  private assertSameCurrency(other: Money): void {
    if (other.currency !== this.currency) {
      throw new Error("amounts must share a currency");
    }
  }
}

// ---- domain/account.ts ----

export class Account {
  private constructor(
    readonly accountId: string,
    readonly ownerId: string,
    private balance: Money,
    readonly dailyTransferLimit: Money,
    private readonly receivedTransferIds: Set<string>,
  ) {}

  static open(
    accountId: string,
    ownerId: string,
    openingBalance: Money,
    dailyTransferLimit: Money,
  ): Account {
    return new Account(
      accountId,
      ownerId,
      openingBalance,
      dailyTransferLimit,
      new Set(),
    );
  }

  get availableBalance(): Money {
    return this.balance;
  }

  withdraw(amount: Money): void {
    if (amount.isGreaterThan(this.balance)) {
      throw new Error("insufficient funds");
    }
    this.balance = this.balance.subtract(amount);
  }

  deposit(amount: Money): void {
    this.balance = this.balance.add(amount);
  }

  receiveTransfer(transferId: string, amount: Money): void {
    if (this.receivedTransferIds.has(transferId)) {
      return;
    }
    this.deposit(amount);
    this.receivedTransferIds.add(transferId);
  }
}

// ---- domain/funds-transferred.ts ----

export class FundsTransferred {
  constructor(
    readonly transferId: string,
    readonly sourceId: string,
    readonly destinationId: string,
    readonly amount: Money,
    readonly on: Date,
  ) {}
}

// ---- domain/transfer-policy.ts ----

// Totals the recorded FundsTransferred events for one source account and day
export interface TransferHistory {
  totalTransferredToday(accountId: string, day: Date): Promise<Money>;
}

export class TransferPolicy {
  constructor(private readonly history: TransferHistory) {}

  async assertPermitted(
    source: Account,
    destination: Account,
    amount: Money,
    day: Date,
  ): Promise<void> {
    if (source.accountId === destination.accountId) {
      throw new Error("source and destination must differ");
    }
    if (
      amount.currency !== source.availableBalance.currency ||
      amount.currency !== destination.availableBalance.currency
    ) {
      throw new Error("cross-currency transfers are not supported");
    }
    const transferredToday = await this.history.totalTransferredToday(
      source.accountId,
      day,
    );
    if (transferredToday.add(amount).isGreaterThan(source.dailyTransferLimit)) {
      throw new Error("daily transfer limit exceeded");
    }
  }
}

// ---- application/transfer-funds.ts ----

export interface AccountRepository {
  findById(accountId: string): Promise<Account | null>;
  // Saves one account and appends its events to the outbox in one transaction
  save(account: Account, events: readonly FundsTransferred[]): Promise<void>;
}

export interface Clock {
  today(): Date;
}

export class TransferFunds {
  constructor(
    private readonly accounts: AccountRepository,
    private readonly policy: TransferPolicy,
    private readonly clock: Clock,
  ) {}

  async execute(
    transferId: string,
    sourceId: string,
    destinationId: string,
    amount: Money,
  ): Promise<void> {
    const source = await this.accounts.findById(sourceId);
    const destination = await this.accounts.findById(destinationId);
    if (!source || !destination) {
      throw new Error("account not found");
    }
    const today = this.clock.today();
    await this.policy.assertPermitted(source, destination, amount, today);
    source.withdraw(amount);
    await this.accounts.save(source, [
      new FundsTransferred(transferId, sourceId, destinationId, amount, today),
    ]);
  }
}

// ---- application/credit-transfer-destination.ts ----

// Credits the destination in its own transaction after the withdrawal commits
export class CreditTransferDestination {
  constructor(private readonly accounts: AccountRepository) {}

  async on(event: FundsTransferred): Promise<void> {
    const destination = await this.accounts.findById(event.destinationId);
    if (!destination) {
      throw new Error("account not found");
    }
    destination.receiveTransfer(event.transferId, event.amount);
    await this.accounts.save(destination, []);
  }
}
