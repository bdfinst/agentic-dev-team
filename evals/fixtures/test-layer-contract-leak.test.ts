import { Pact } from "@pact-foundation/pact";
import { PricingClient } from "../clients/PricingClient";

// Contract test: consumer expectations against the pricing provider.
const provider = new Pact({ consumer: "checkout", provider: "pricing" });

describe("pricing contract", () => {
  it("returns the gold discount", async () => {
    await provider.addInteraction({
      state: "customer is gold tier with a 100.00 cart",
      uponReceiving: "a quote request",
      withRequest: { method: "POST", path: "/quotes", body: { tier: "gold", amount: 100 } },
      willRespondWith: { status: 200, body: { total: 85, discount: 15 } },
    });
    const quote = await new PricingClient(provider.mockService.baseUrl).quote("gold", 100);
    // Asserts the computed business value, not the interface shape.
    expect(quote.discount).toBe(15);
    expect(quote.total).toBe(85);
  });
});
