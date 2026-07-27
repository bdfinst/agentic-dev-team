import { OrderService } from "../domain/OrderService";

// Smell: mocking a collaborator internal to / owned by the same
// order-processing bounded context as the SUT. WalletService is not a
// third-party API or another team's service — it lives in the same
// component as OrderService and should be exercised as real (sociable
// component test), not doubled.
describe("OrderService", () => {
  it("charges the customer's wallet when an order is placed", () => {
    const wallet = { debit: jest.fn().mockReturnValue({ ok: true }) };
    const inventory = { reserve: jest.fn().mockReturnValue({ ok: true }) };

    const service = new OrderService(wallet, inventory);
    const result = service.placeOrder({ customerId: "c1", total: 42 });

    expect(wallet.debit).toHaveBeenCalledWith("c1", 42);
    expect(result.status).toBe("placed");
  });
});
