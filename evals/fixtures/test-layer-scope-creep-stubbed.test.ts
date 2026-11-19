import nock from "nock";
import request from "supertest";
import { createApp } from "../app";

describe("order component", () => {
  it("reserves stock via a stubbed inventory service", async () => {
    nock("https://inventory.example.com").post("/api/reserve").reply(200, { ok: true });
    const app = createApp({ inventoryUrl: "https://inventory.example.com/api" });
    const res = await request(app).post("/orders").send({ sku: "A-1", qty: 2 });
    expect(res.status).toBe(201);
  });

  it("calls a loopback notifier", async () => {
    nock("http://127.0.0.1:4010").post("/notify").reply(204);
    const app = createApp({ notifierUrl: "http://127.0.0.1:4010" });
    const res = await request(app).post("/orders").send({ sku: "B-2", qty: 1 });
    expect(res.status).toBe(201);
  });
});
