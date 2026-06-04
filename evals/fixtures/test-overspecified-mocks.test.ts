import { PricingService } from "../domain/PricingService";

// Smell: Overspecified Software — the test pins down the exact internal
// call sequence via mocks instead of asserting the outcome. A Stub plus a
// state assertion on the returned price would verify the real behavior
// without coupling to how PricingService is implemented.
describe("PricingService", () => {
  it("prices an order", () => {
    const taxCalc = { calculate: jest.fn().mockReturnValue(5) };
    const discountCalc = { calculate: jest.fn().mockReturnValue(2) };
    const rounding = { round: jest.fn((n: number) => n) };

    const service = new PricingService(taxCalc, discountCalc, rounding);
    service.priceOrder({ subtotal: 100 });

    // Asserting internal mechanics, not the result:
    expect(discountCalc.calculate).toHaveBeenCalledBefore(taxCalc.calculate);
    expect(taxCalc.calculate).toHaveBeenCalledTimes(1);
    expect(taxCalc.calculate).toHaveBeenCalledWith(98);
    expect(rounding.round).toHaveBeenCalledTimes(1);
    // Nowhere is the actual final price asserted.
  });
});
