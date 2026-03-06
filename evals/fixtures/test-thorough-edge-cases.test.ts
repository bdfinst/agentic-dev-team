import { parseUserInput } from "../parser";

describe("parseUserInput", () => {
  // Happy path
  it("parses a valid name and age", () => {
    const result = parseUserInput("Alice", "30");

    expect(result).toEqual({ name: "Alice", age: 30 });
  });

  it("trims whitespace from name", () => {
    const result = parseUserInput("  Bob  ", "25");

    expect(result.name).toBe("Bob");
  });

  // Null / undefined
  it("returns error result when name is null", () => {
    const result = parseUserInput(null as unknown as string, "30");

    expect(result.error).toBe("name is required");
    expect(result.name).toBeUndefined();
  });

  it("returns error result when age is undefined", () => {
    const result = parseUserInput("Alice", undefined as unknown as string);

    expect(result.error).toBe("age is required");
  });

  // Empty / blank
  it("rejects an empty string name", () => {
    const result = parseUserInput("", "30");

    expect(result.error).toBe("name must not be empty");
  });

  it("rejects a whitespace-only name", () => {
    const result = parseUserInput("   ", "30");

    expect(result.error).toBe("name must not be empty");
  });

  // Boundary values
  it("accepts age at the minimum boundary (0)", () => {
    const result = parseUserInput("Baby", "0");

    expect(result.age).toBe(0);
    expect(result.error).toBeUndefined();
  });

  it("accepts age at the maximum boundary (150)", () => {
    const result = parseUserInput("Elder", "150");

    expect(result.age).toBe(150);
    expect(result.error).toBeUndefined();
  });

  it("rejects negative age", () => {
    const result = parseUserInput("Alice", "-1");

    expect(result.error).toBe("age must be between 0 and 150");
  });

  it("rejects age above maximum", () => {
    const result = parseUserInput("Alice", "151");

    expect(result.error).toBe("age must be between 0 and 150");
  });

  // Error path — non-numeric
  it("rejects non-numeric age string", () => {
    const result = parseUserInput("Alice", "abc");

    expect(result.error).toBe("age must be a number");
  });

  it("rejects age with decimal value", () => {
    const result = parseUserInput("Alice", "25.5");

    expect(result.error).toBe("age must be a whole number");
  });
});
