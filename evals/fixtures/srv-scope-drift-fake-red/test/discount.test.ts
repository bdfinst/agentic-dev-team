import { describe, expect, it } from "vitest";
import { applyDiscount } from "../src/checkout/discount";

describe("applyDiscount", () => {
  it("reduces the total for a valid code", () => {
    const r = applyDiscount({ total: 80 }, { code: "AUTUMN15", percent: 15, expires: "2026-11-30" }, "2026-11-14");
    expect(r.ok).toBe(true);
    expect(r.cart.total).toBe(68);
  });

  it("rejects an expired code", () => {
    const r = applyDiscount({ total: 80 }, { code: "SUMMER10", percent: 10, expires: "2026-08-31" }, "2026-11-14");
    expect(r.ok).toBe(false);
    expect(r.ok === false && r.message).toBe("Coupon has expired");
    expect(r.cart.total).toBe(80);
  });
});
