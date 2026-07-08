// ORACLE PROVENANCE — INDEPENDENT/SPEC-DERIVED: all expected values have
// external justification. Expected: no circular-oracle findings.

import { describe, it, expect } from 'vitest';

// System under test
function celsiusToFahrenheit(c: number): number {
  return (c * 9) / 5 + 32;
}

function base64Encode(input: string): string {
  return Buffer.from(input).toString('base64');
}

describe('celsiusToFahrenheit', () => {
  // SPEC-DERIVED: water freezing point per SI standard — 0°C = 32°F
  it('converts freezing point', () => {
    expect(celsiusToFahrenheit(0)).toBe(32);
  });

  // SPEC-DERIVED: water boiling point per SI standard — 100°C = 212°F
  it('converts boiling point', () => {
    expect(celsiusToFahrenheit(100)).toBe(212);
  });

  // INDEPENDENT: hand calculation — (37 * 9/5) + 32 = 66.6 + 32 = 98.6
  it('converts body temperature', () => {
    expect(celsiusToFahrenheit(37)).toBeCloseTo(98.6, 1);
  });
});

describe('base64Encode', () => {
  // SPEC-DERIVED: RFC 4648 §10 test vector — "Man" encodes to "TWFu"
  it('encodes ASCII string per RFC 4648 test vector', () => {
    expect(base64Encode('Man')).toBe('TWFu');
  });

  // SPEC-DERIVED: RFC 4648 §10 — empty string encodes to empty string
  it('encodes empty string', () => {
    expect(base64Encode('')).toBe('');
  });
});
