import { describe, expect, it } from "vitest";
import request from "supertest";
import express from "express";
import { shipmentsRouter } from "../src/routes/shipments";

const app = express().use(express.json()).use("/shipments", shipmentsRouter);

describe("POST /shipments", () => {
  it("rejects a tracking number shorter than 8 characters", async () => {
    const response = await request(app).post("/shipments").send({ carrier: "ups", trackingNumber: "1Z12" });
    expect(response.status).toBe(400);
  });
});
