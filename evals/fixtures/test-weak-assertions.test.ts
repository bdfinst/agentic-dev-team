import { UserService } from "../services/UserService";

describe("UserService", () => {
  const service = new UserService();

  it("should get a user", async () => {
    const user = await service.getById("user-1");

    // Weak: toBeTruthy instead of checking actual value
    expect(user).toBeTruthy();
    expect(user.name).toBeTruthy();
    expect(user.email).toBeTruthy();
  });

  it("should create a user", async () => {
    const user = await service.create({ name: "Alice", email: "a@b.com" });

    // Weak: only checks truthiness, not the actual shape or values
    expect(user.id).toBeTruthy();
    expect(user).toBeTruthy();
  });

  it("should have the internal cache populated after fetch", async () => {
    await service.getById("user-1");

    // Testing implementation detail: checking private cache
    expect((service as any)._cache.size).toBeGreaterThan(0);
    expect((service as any)._cache.has("user-1")).toBeTruthy();
  });

  it("should call the repository save method", async () => {
    const spy = jest.spyOn((service as any).repo, "save");

    await service.create({ name: "Bob", email: "bob@test.com" });

    // Testing implementation: verifying internal method calls
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls[0][0].name).toBeTruthy();
  });

  it("should return something for search", async () => {
    const results = await service.search("ali");

    // Weak: no assertion on content, count, or structure
    expect(results).toBeTruthy();
    expect(results.length).toBeTruthy();
  });
});
