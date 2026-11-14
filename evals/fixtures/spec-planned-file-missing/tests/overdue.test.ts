import { describe, it, expect } from "vitest";
import { markOverdue, type Invoice } from "../src/overdue";

const now = new Date("2026-05-20T00:00:00Z");

function invoice(dueDate: string, paid = false): Invoice {
  return { id: "inv-1", dueDate: new Date(dueDate), paid, overdue: false };
}

describe("markOverdue", () => {
  it("marks an invoice unpaid 8 days after its due date as overdue", () => {
    const [result] = markOverdue([invoice("2026-05-12T00:00:00Z")], now);
    expect(result.overdue).toBe(true);
  });

  it("leaves an invoice 6 days past due alone", () => {
    const [result] = markOverdue([invoice("2026-05-14T00:00:00Z")], now);
    expect(result.overdue).toBe(false);
  });

  it("never marks a paid invoice overdue", () => {
    const [result] = markOverdue([invoice("2026-04-01T00:00:00Z", true)], now);
    expect(result.overdue).toBe(false);
  });
});
