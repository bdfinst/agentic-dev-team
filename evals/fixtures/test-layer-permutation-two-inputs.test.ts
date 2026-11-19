import request from "supertest";
import { createApp } from "../app";

describe("POST /quotes component", () => {
  const app = createApp({ repo: "in-memory" });

  it("applies the member discount", async () => {
    const res = await request(app).post("/quotes").send({ tier: "gold", amount: 100 });
    expect(res.body.total).toBe(85);
  });
  it("charges full price to a guest", async () => {
    const res = await request(app).post("/quotes").send({ tier: "guest", amount: 100 });
    expect(res.body.total).toBe(100);
  });
});
