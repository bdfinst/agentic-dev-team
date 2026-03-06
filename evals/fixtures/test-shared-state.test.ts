import { CartService } from "../services/CartService";
import { ProductApi } from "../api/ProductApi";

// Shared mutable state — not reset between tests
let cart = new CartService();
const mockApi = new ProductApi("http://fake");
jest.spyOn(mockApi, "fetchProduct").mockResolvedValue({
  id: "prod-1",
  name: "Gadget",
  price: 29.99,
});

describe("CartService", () => {
  // No beforeEach to reset cart or clear mocks

  it("adds a product to the cart", async () => {
    await cart.addItem("prod-1", mockApi);

    expect(cart.items).toHaveLength(1);
    expect(cart.total).toBe(29.99);
  });

  it("calculates total for multiple items", async () => {
    // Depends on state from previous test — cart already has 1 item
    await cart.addItem("prod-1", mockApi);

    // This will be 2 items (59.98) only if the previous test ran first
    expect(cart.items).toHaveLength(2);
    expect(cart.total).toBe(59.98);
  });

  it("removes an item from the cart", async () => {
    // Still depends on accumulated state from above
    cart.removeItem("prod-1");

    expect(cart.items).toHaveLength(1);
  });

  it("verifies the mock was called the right number of times", () => {
    // Mock call count leaks across tests because it was never reset
    expect(mockApi.fetchProduct).toHaveBeenCalledTimes(2);
  });
});
