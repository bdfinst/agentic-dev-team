import { OrderSummary } from "../domain/OrderSummary";

// Smell: Assertion Roulette (many bare assertions, no messages) +
// Eager Test (one test exercises many unrelated behaviors).
describe("OrderSummary", () => {
  it("works", () => {
    const summary = new OrderSummary([
      { sku: "A", qty: 2, price: 10 },
      { sku: "B", qty: 1, price: 5 },
    ]);

    // Many unrelated behaviors crammed into one test; on failure you
    // cannot tell which assertion broke — no messages, no isolation.
    expect(summary.itemCount).toBe(3);
    expect(summary.subtotal).toBe(25);
    expect(summary.tax).toBe(2.5);
    expect(summary.total).toBe(27.5);
    expect(summary.isEmpty).toBe(false);
    expect(summary.heaviestLine().sku).toBe("A");
    expect(summary.format()).toContain("27.50");
    expect(summary.discountApplied).toBe(false);
  });
});
