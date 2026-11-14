import { describe, expect, it } from "vitest";
import { formatCurrency } from "./formatCurrency";

describe("formatCurrency", () => {
  it("formats cents as dollars with two decimals", () => {
    expect(formatCurrency(123456)).toBe("$1234.56");
  });
});
