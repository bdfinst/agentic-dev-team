import { OrderService } from "../domain/OrderService";

// Smell: mocking a collaborator internal to / owned by the same
// order-processing component/bounded context as the SUT.
// OrderPricingCalculator is a pure, in-process calculator that lives in
// the same component as OrderService — it has no I/O and no external
// boundary of its own — so it should be exercised as real (sociable
// component test), not doubled.
describe("OrderService", () => {
  it("applies the pricing calculator's total when an order is placed", () => {
    const pricingCalculator = {
      calculateTotal: jest.fn().mockReturnValue(42),
    };
    const inventory = { reserve: jest.fn().mockReturnValue({ ok: true }) };

    const service = new OrderService(pricingCalculator, inventory);
    const result = service.placeOrder({ customerId: "c1", items: [] });

    expect(pricingCalculator.calculateTotal).toHaveBeenCalledWith({
      customerId: "c1",
      items: [],
    });
    expect(result.status).toBe("placed");
  });
});
