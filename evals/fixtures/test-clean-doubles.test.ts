import { PricingService } from "../domain/PricingService";

// Clean control: a stub supplies controlled inputs and the test asserts on
// the SUT's returned state (state verification). One behavior per test,
// clear arrange-act-assert, named expected values. No smells to flag.
describe("PricingService", () => {
  const fixedTax = { calculate: (n: number) => n * 0.1 };
  const noDiscount = { calculate: () => 0 };
  const exactRounding = { round: (n: number) => n };

  function makeService() {
    return new PricingService(fixedTax, noDiscount, exactRounding);
  }

  it("adds tax to the subtotal", () => {
    const price = makeService().priceOrder({ subtotal: 100 });

    expect(price.total).toBe(110);
  });

  it("returns the subtotal unchanged when tax is zero", () => {
    const taxFree = new PricingService(
      { calculate: () => 0 },
      noDiscount,
      exactRounding,
    );

    const price = taxFree.priceOrder({ subtotal: 100 });

    expect(price.total).toBe(100);
  });
});
