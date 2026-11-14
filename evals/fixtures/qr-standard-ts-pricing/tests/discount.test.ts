import { describe, expect, it } from "vitest";
import { loyaltyDiscount } from "../src/pricing/discount";

describe("loyaltyDiscount", () => {
  it("gives gold members 10% at or above $100", () => {
    expect(loyaltyDiscount(10000, "gold")).toBe(1000);
  });
  it("gives nothing below $100", () => {
    expect(loyaltyDiscount(9999, "gold")).toBe(0);
  });
});
