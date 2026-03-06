import { DiscountCalculator } from "../pricing/DiscountCalculator";

describe("DiscountCalculator", () => {
  const calc = new DiscountCalculator();

  it("applies 10% discount for orders over $100", () => {
    const result = calc.calculate({ subtotal: 200, customerTier: "gold" });

    expect(result.discount).toBe(20);
    expect(result.finalPrice).toBe(180);
  });

  it("applies 5% discount for silver tier", () => {
    const result = calc.calculate({ subtotal: 200, customerTier: "silver" });

    expect(result.discount).toBe(10);
    expect(result.finalPrice).toBe(190);
  });

  it("gives no discount for basic tier", () => {
    const result = calc.calculate({ subtotal: 200, customerTier: "basic" });

    expect(result.discount).toBe(0);
    expect(result.finalPrice).toBe(200);
  });

  it("applies percentage coupon on top of tier discount", () => {
    const result = calc.calculate({
      subtotal: 100,
      customerTier: "gold",
      couponCode: "SAVE5",
    });

    expect(result.discount).toBe(15);
    expect(result.finalPrice).toBe(85);
  });

  // Missing: null/undefined subtotal
  // Missing: negative subtotal
  // Missing: zero subtotal
  // Missing: subtotal at exact discount threshold boundary ($100)
  // Missing: unknown customerTier value
  // Missing: invalid or expired couponCode
  // Missing: extremely large subtotal (overflow)
});
