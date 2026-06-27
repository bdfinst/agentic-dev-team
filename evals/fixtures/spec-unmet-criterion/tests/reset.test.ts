import { describe, it, expect } from "vitest";
import { requestReset } from "../src/reset";

// Only criterion 1 has a test. Criterion 2 (expiry), criterion 3 (no
// enumeration), and the "Expired reset link is rejected" scenario have no
// coverage.
describe("password reset", () => {
  it("sends a reset link for a known email", async () => {
    const store = {
      findUserByEmail: async () => ({ id: "u1" }),
      saveToken: async () => {},
    };
    expect(await requestReset("a@b.com", store)).toBe("reset link sent");
  });
});
