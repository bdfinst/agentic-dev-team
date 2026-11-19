import request from "supertest";
import { createApp } from "../app";

// Component test: real app, in-memory repository.
describe("POST /quotes component", () => {
  const app = createApp({ repo: "in-memory" });

  it("applies the bronze discount", async () => {
    const res = await request(app).post("/quotes").send({ tier: "bronze", amount: 100 });
    expect(res.body.total).toBe(95);
  });
  it("applies the silver discount", async () => {
    const res = await request(app).post("/quotes").send({ tier: "silver", amount: 100 });
    expect(res.body.total).toBe(90);
  });
  it("applies the gold discount", async () => {
    const res = await request(app).post("/quotes").send({ tier: "gold", amount: 100 });
    expect(res.body.total).toBe(85);
  });
});
