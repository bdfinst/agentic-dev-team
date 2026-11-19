import request from "supertest";
import { createApp } from "../app";

// docker-compose.yml defines the `inventory` service; the host name is resolved
// by the compose network, not by this test.
describe("order component", () => {
  const app = createApp({ inventoryUrl: "http://inventory:8080" });

  it("reserves stock for an order", async () => {
    const res = await request(app).post("/orders").send({ sku: "A-1", qty: 2 });
    expect(res.status).toBe(201);
  });
});
