import { PricingService } from "../domain/PricingService";

// Smell: Overspecified Software — beyond the outcome, the test pins down the
// exact internal call sequence via mocks. A Stub plus the state assertion on
// the returned price already verifies the behavior without coupling to how
// PricingService is implemented.
describe("PricingService", () => {
  it("prices an order", () => {
    const taxCalc = { calculate: jest.fn().mockReturnValue(5) };
    const discountCalc = { calculate: jest.fn().mockReturnValue(2) };
    const rounding = { round: jest.fn((n: number) => n) };

    const service = new PricingService(taxCalc, discountCalc, rounding);
    const price = service.priceOrder({ subtotal: 100 });

    expect(price).toBe(103);

    // Asserting internal mechanics on top of the result:
    expect(discountCalc.calculate).toHaveBeenCalledBefore(taxCalc.calculate);
    expect(taxCalc.calculate).toHaveBeenCalledTimes(1);
    expect(taxCalc.calculate).toHaveBeenCalledWith(98);
    expect(rounding.round).toHaveBeenCalledTimes(1);
  });
});
