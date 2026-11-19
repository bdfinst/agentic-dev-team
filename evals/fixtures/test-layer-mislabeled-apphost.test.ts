import request from "supertest";
import { createApp } from "../app";

// "unit" tests for the orders endpoint
describe("orders unit", () => {
  it("returns 201 for a valid order", async () => {
    const app = createApp({ repo: "in-memory" });
    const res = await request(app).post("/orders").send({ sku: "A-1", qty: 1 });
    expect(res.status).toBe(201);
  });
});
