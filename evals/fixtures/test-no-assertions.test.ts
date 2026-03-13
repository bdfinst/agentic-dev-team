import { RefundService } from "../services/RefundService";
import { OrderRepository } from "../repositories/OrderRepository";

describe("RefundService", () => {
  const service = new RefundService(new OrderRepository());

  it("should handle null refund request", async () => {
    // Calls the method but never checks the result
    await service.processRefund(null as any);
  });

  it("should process a valid refund", async () => {
    const result = await service.processRefund({
      orderId: "order-123",
      amount: 50.0,
      reason: "defective",
    });

    // Has assertions — this one is fine
    expect(result.status).toBe("approved");
    expect(result.refundedAmount).toBe(50.0);
  });

  it("should handle duplicate refund requests", async () => {
    // Exercises the code path but asserts nothing
    await service.processRefund({
      orderId: "order-123",
      amount: 50.0,
      reason: "defective",
    });
    await service.processRefund({
      orderId: "order-123",
      amount: 50.0,
      reason: "defective",
    });
  });

  it("should cancel a refund", () => {
    // Calls cancel but never checks outcome
    service.cancelRefund("refund-456");
  });

  it("should calculate partial refund amount", () => {
    const amount = service.calculatePartialRefund("order-789", 0.5);
    // amount is computed but never asserted
    console.log("Partial refund:", amount);
  });

  it("should validate refund eligibility", async () => {
    const eligible = await service.checkEligibility("order-999");
    // Result captured in variable but no assertion
  });

  it("should reject refund for shipped orders", async () => {
    const result = await service.processRefund({
      orderId: "order-shipped",
      amount: 100.0,
      reason: "changed mind",
    });

    // Good: actually asserts the rejection
    expect(result.status).toBe("rejected");
    expect(result.reason).toContain("already shipped");
  });
});
