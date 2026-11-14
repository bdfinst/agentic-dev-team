import { RenewalService } from "../src/renewal-service";
import type { Subscription } from "../src/subscription";

const MARCH_FIRST_2026 = new Date("2026-03-01T12:00:00Z");
const fixedClock = () => MARCH_FIRST_2026;

function aSubscription(overrides: Partial<Subscription> = {}): Subscription {
  return {
    id: "sub-1",
    plan: "monthly",
    endsAt: new Date("2026-03-15T00:00:00Z"),
    autoRenew: true,
    cancelledAt: null,
    ...overrides,
  };
}

describe("RenewalService", () => {
  describe("isActive", () => {
    it("treats a subscription as active before its end date", () => {
      const service = new RenewalService(fixedClock);

      expect(service.isActive(aSubscription())).toBe(true);
    });

    it("treats a subscription as inactive after its end date", () => {
      const service = new RenewalService(fixedClock);
      const ended = aSubscription({ endsAt: new Date("2026-02-28T00:00:00Z") });

      expect(service.isActive(ended)).toBe(false);
    });

    it("keeps an annual plan active until the end of the year", () => {
      const service = new RenewalService();
      const annual = aSubscription({
        plan: "annual",
        endsAt: new Date("2026-12-31T00:00:00Z"),
      });

      expect(service.isActive(annual)).toBe(true);
    });
  });

  describe("isRenewalDue", () => {
    it("is due within seven days of the end date when auto-renew is on", () => {
      const service = new RenewalService(fixedClock);
      const endsInSixDays = aSubscription({
        endsAt: new Date("2026-03-07T12:00:00Z"),
      });

      expect(service.isRenewalDue(endsInSixDays)).toBe(true);
    });

    it("is not due when auto-renew is off", () => {
      const service = new RenewalService(fixedClock);
      const manual = aSubscription({
        endsAt: new Date("2026-03-07T12:00:00Z"),
        autoRenew: false,
      });

      expect(service.isRenewalDue(manual)).toBe(false);
    });

    it("is not due for a cancelled subscription", () => {
      const service = new RenewalService(fixedClock);
      const cancelled = aSubscription({
        endsAt: new Date("2026-03-07T12:00:00Z"),
        cancelledAt: new Date("2026-02-20T09:30:00Z"),
      });

      expect(service.isRenewalDue(cancelled)).toBe(false);
    });
  });

  describe("nextEndDate", () => {
    it("extends a monthly plan by one calendar month", () => {
      const service = new RenewalService(fixedClock);

      const next = service.nextEndDate(aSubscription());

      expect(next).toEqual(new Date("2026-04-15T00:00:00Z"));
    });

    it("extends an annual plan by one calendar year", () => {
      const service = new RenewalService(fixedClock);
      const annual = aSubscription({ plan: "annual" });

      const next = service.nextEndDate(annual);

      expect(next).toEqual(new Date("2027-03-15T00:00:00Z"));
    });
  });
});
