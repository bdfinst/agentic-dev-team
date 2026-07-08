import { PricingEngine } from "../services/PricingEngine";

describe("PricingEngine", () => {
  it("computes the discount tier by reaching into the private method", () => {
    const engine = new PricingEngine();

    // Reaches around encapsulation instead of testing through the public API
    const tier = (engine as any)["_computeDiscountTier"](450);

    expect(tier).toBe("gold");
  });

  it("applies a discount through the public API", () => {
    const engine = new PricingEngine();

    const total = engine.applyDiscount(450);

    expect(total).toBeCloseTo(382.5);
  });
});
