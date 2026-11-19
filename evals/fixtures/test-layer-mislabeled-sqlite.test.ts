import Database from "better-sqlite3";
import { OrderRepository } from "../repo/OrderRepository";

describe("OrderRepository unit", () => {
  it("saves and loads an order", () => {
    const db = new Database(":memory:");
    const repo = new OrderRepository(db);

    repo.save({ id: "o-1", total: 50 });

    expect(repo.find("o-1").total).toBe(50);
  });
});
