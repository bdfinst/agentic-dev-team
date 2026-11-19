import { Pact, Matchers } from "@pact-foundation/pact";
import { PricingClient } from "../clients/PricingClient";

const provider = new Pact({ consumer: "checkout", provider: "pricing" });

describe("pricing contract", () => {
  it("returns a quote with the expected shape", async () => {
    await provider.addInteraction({
      state: "a quote can be created",
      uponReceiving: "a quote request",
      withRequest: { method: "POST", path: "/quotes", body: { tier: "gold", amount: 100 } },
      willRespondWith: {
        status: 200,
        body: { total: Matchers.decimal(85), discount: Matchers.decimal(15) },
      },
    });
    const quote = await new PricingClient(provider.mockService.baseUrl).quote("gold", 100);
    expect(typeof quote.total).toBe("number");
    expect(typeof quote.discount).toBe("number");
  });
});
