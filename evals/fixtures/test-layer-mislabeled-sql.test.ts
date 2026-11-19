import { Client } from "pg";
import { OrderRepository } from "../repo/OrderRepository";

// Unit tests for OrderRepository
describe("OrderRepository unit", () => {
  it("saves and loads an order", async () => {
    const client = new Client({ connectionString: process.env.DATABASE_URL });
    await client.connect();
    const repo = new OrderRepository(client);

    await repo.save({ id: "o-1", total: 50 });
    const loaded = await repo.find("o-1");

    expect(loaded.total).toBe(50);
    await client.end();
  });
});
