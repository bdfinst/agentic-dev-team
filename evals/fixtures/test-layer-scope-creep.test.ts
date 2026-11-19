import request from "supertest";
import { createApp } from "../app";

// Component test, but the downstream is a real remote host.
describe("order component", () => {
  const app = createApp({ inventoryUrl: "https://inventory.example.com/api" });

  it("reserves stock for an order", async () => {
    const res = await request(app).post("/orders").send({ sku: "A-1", qty: 2 });
    expect(res.status).toBe(201);
    expect(res.body.reserved).toBe(true);
  });
});
