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

// ---- domain/transfer-events.ts ----

export class TransferSent {
  constructor(
    readonly transferId: string,
    readonly sourceId: string,
    readonly destinationId: string,
    readonly amount: Money,
    readonly sentOn: Date,
  ) {}
}

export class TransferReturned {
  constructor(
    readonly transferId: string,
    readonly sourceId: string,
    readonly amount: Money,
  ) {}
}

export type AccountEvent = TransferSent | TransferReturned;

// ---- domain/account.ts ----

export class Account {
  private readonly pendingEvents: AccountEvent[] = [];

  private constructor(
    readonly accountId: string,
    readonly ownerId: string,
    private balance: Money,
    readonly dailyTransferLimit: Money,
    private readonly sentTransfers: Map<string, Money>,
    private readonly receivedTransferIds: Set<string>,
    private readonly returnedTransferIds: Set<string>,
  ) {}

  static open(
    accountId: string,
    ownerId: string,
    openingBalance: Money,
    dailyTransferLimit: Money,
  ): Account {
    if (dailyTransferLimit.currency !== openingBalance.currency) {
      throw new Error("the daily limit must use the account's currency");
    }
    return new Account(
      accountId,
      ownerId,
      openingBalance,
      dailyTransferLimit,
      new Map(),
      new Set(),
      new Set(),
    );
  }

  get currency(): string {
    return this.balance.currency;
  }

  get availableBalance(): Money {
    return this.balance;
  }

  hasSent(transferId: string): boolean {
    return this.sentTransfers.has(transferId);
  }

  sendTransfer(
    transferId: string,
    destinationId: string,
    amount: Money,
    sentOn: Date,
  ): void {
    if (this.hasSent(transferId)) {
      throw new Error(`transfer ${transferId} was already sent`);
    }
    if (amount.isGreaterThan(this.balance)) {
      throw new Error("insufficient funds");
    }
    this.balance = this.balance.subtract(amount);
    this.sentTransfers.set(transferId, amount);
    this.pendingEvents.push(
      new TransferSent(transferId, this.accountId, destinationId, amount, sentOn),
    );
  }

  receiveTransfer(transferId: string, amount: Money): void {
    if (this.receivedTransferIds.has(transferId)) {
      return;
    }
    this.balance = this.balance.add(amount);
    this.receivedTransferIds.add(transferId);
  }

  // Refunds a sent transfer that the destination could not accept
  returnTransfer(transferId: string): void {
    const amount = this.sentTransfers.get(transferId);
    if (!amount) {
      throw new Error(`transfer ${transferId} was never sent`);
    }
    if (this.returnedTransferIds.has(transferId)) {
      return;
    }
    this.balance = this.balance.add(amount);
    this.returnedTransferIds.add(transferId);
    this.pendingEvents.push(
      new TransferReturned(transferId, this.accountId, amount),
    );
  }

  get raisedEvents(): readonly AccountEvent[] {
    return this.pendingEvents;
  }

  // Called by the repository once the raised events are in the outbox
  clearRaisedEvents(): void {
    this.pendingEvents.length = 0;
  }
}

// ---- domain/transfer-policy.ts ----

// Totals the TransferSent events, less any returned, for one source account and day
export interface TransferHistory {
  totalSentOn(accountId: string, day: Date): Promise<Money>;
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
      amount.currency !== source.currency ||
      amount.currency !== destination.currency
    ) {
      throw new Error("cross-currency transfers are not supported");
    }
    const sentToday = await this.history.totalSentOn(source.accountId, day);
    if (sentToday.add(amount).isGreaterThan(source.dailyTransferLimit)) {
      throw new Error("daily transfer limit exceeded");
    }
  }
}

// ---- application/transfer-funds.ts ----

export interface AccountRepository {
  findById(accountId: string): Promise<Account | null>;
  // Saves one account and appends its raised events to the outbox in one
  // transaction; rejects a stale account version, so two concurrent sends from
  // one account cannot both pass the daily limit
  save(account: Account): Promise<void>;
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
    // A retried command is a no-op, checked before the policy counts it twice
    if (source.hasSent(transferId)) {
      return;
    }
    const today = this.clock.today();
    await this.policy.assertPermitted(source, destination, amount, today);
    source.sendTransfer(transferId, destinationId, amount, today);
    await this.accounts.save(source);
  }
}

// ---- application/credit-transfer-destination.ts ----

// Credits the destination in its own transaction after the send commits, and
// returns the funds to the source when the destination cannot accept them
export class CreditTransferDestination {
  constructor(private readonly accounts: AccountRepository) {}

  async handle(event: TransferSent): Promise<void> {
    const destination = await this.accounts.findById(event.destinationId);
    if (destination && destination.currency === event.amount.currency) {
      destination.receiveTransfer(event.transferId, event.amount);
      await this.accounts.save(destination);
      return;
    }
    const source = await this.accounts.findById(event.sourceId);
    if (!source) {
      throw new Error(`source account ${event.sourceId} not found`);
    }
    source.returnTransfer(event.transferId);
    await this.accounts.save(source);
  }
}
