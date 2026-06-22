// CONSISTENCY CANONICAL: exactly 3 error/warning violations, 1 suggestion.
// Designed to produce a stable finding count across repeated runs.
// Issues are unambiguous — each maps to a single, named detect rule.

import { describe, it, expect } from 'vitest';

function add(a: number, b: number): number {
  return a + b;
}

function divide(a: number, b: number): number {
  if (b === 0) throw new Error('Division by zero');
  return a / b;
}

describe('add', () => {
  // issue (error): no assertion — exercises the function but asserts nothing
  it('adds two numbers', () => {
    add(1, 2);
  });

  // issue (warning): truthiness-only assertion — passes on any non-null value
  it('returns a number', () => {
    expect(add(1, 2)).toBeTruthy();
  });

  // issue (suggestion): misleading test name — 'test 1' reveals nothing
  it('test 1', () => {
    expect(add(0, 0)).toBe(0);
  });
});

describe('divide', () => {
  // issue (error): missing error-path test for the division-by-zero guard
  it('divides two numbers', () => {
    expect(divide(10, 2)).toBe(5);
  });

  it('throws on division by zero', () => {
    expect(() => divide(1, 0)).toThrow('Division by zero');
  });
});
