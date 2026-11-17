import axios from "axios";

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
    if (other.currency !== this.currency) {
      throw new Error("cannot add amounts in different currencies");
    }
    return Money.ofCents(this.amountCents + other.amountCents, this.currency);
  }
}

// ---- domain/membership.ts ----

export type MembershipTier = "standard" | "premium";

export class MembershipRenewed {
  constructor(
    readonly membershipId: string,
    readonly tier: MembershipTier,
    readonly price: Money,
    readonly expiresOn: Date,
  ) {}
}

export class Membership {
  private constructor(
    readonly membershipId: string,
    readonly memberId: string,
    private tier: MembershipTier,
    private expiresOn: Date,
    private cancelled: boolean,
  ) {}

  static enroll(
    membershipId: string,
    memberId: string,
    tier: MembershipTier,
    expiresOn: Date,
  ): Membership {
    return new Membership(
      membershipId,
      memberId,
      tier,
      new Date(expiresOn),
      false,
    );
  }

  get currentTier(): MembershipTier {
    return this.tier;
  }

  get expiry(): Date {
    return new Date(this.expiresOn);
  }

  upgradeToPremium(): void {
    if (this.cancelled) {
      throw new Error("a cancelled membership cannot be upgraded");
    }
    this.tier = "premium";
  }

  cancel(): void {
    this.cancelled = true;
  }

  async renew(renewalTermMonths: number): Promise<MembershipRenewed> {
    if (this.cancelled) {
      throw new Error("a cancelled membership cannot be renewed");
    }
    if (!Number.isInteger(renewalTermMonths) || renewalTermMonths <= 0) {
      throw new RangeError("renewalTermMonths must be a positive integer");
    }
    const response = await axios.get<{ amountCents: number; currency: string }>(
      `https://pricing.internal/api/tiers/${this.tier}/price`,
    );
    const price = Money.ofCents(
      response.data.amountCents,
      response.data.currency,
    );
    const nextExpiry = new Date(this.expiresOn);
    nextExpiry.setMonth(nextExpiry.getMonth() + renewalTermMonths);
    this.expiresOn = nextExpiry;
    return new MembershipRenewed(
      this.membershipId,
      this.tier,
      price,
      new Date(nextExpiry),
    );
  }
}

// ---- application/renew-membership.ts ----

export interface MembershipRepository {
  findById(membershipId: string): Promise<Membership | null>;
  // Saves the membership and appends its events to the outbox in one transaction
  save(
    membership: Membership,
    events: readonly MembershipRenewed[],
  ): Promise<void>;
}

export class RenewMembership {
  constructor(private readonly memberships: MembershipRepository) {}

  async execute(
    membershipId: string,
    renewalTermMonths: number,
  ): Promise<void> {
    const membership = await this.memberships.findById(membershipId);
    if (!membership) {
      throw new Error(`membership ${membershipId} not found`);
    }
    const renewed = await membership.renew(renewalTermMonths);
    await this.memberships.save(membership, [renewed]);
  }
}
