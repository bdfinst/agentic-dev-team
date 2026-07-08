// UNARMORED REGION FIXTURE: demonstrates the distinction between an ordinary
// coverage gap (some tests exist, a path is missing) and an unarmored region
// (no tests AND no sign of historical defensive attention).
//
// Expected findings:
//   - parseConfig: UNARMORED REGION — no tests at all, no defensive comments
//   - validateEmail: ordinary COVERAGE GAP — happy path tested, error paths missing

import { describe, it, expect } from 'vitest';

// -----------------------------------------------------------------------
// Code under test
// -----------------------------------------------------------------------

/**
 * Parses a configuration string of the form "key=value;key=value".
 * This function has never been tested and has no defensive comments,
 * error-handling annotations, or related test utilities. It is unarmored.
 */
export function parseConfig(raw: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const pair of raw.split(';')) {
    const [k, v] = pair.split('=');
    result[k.trim()] = v.trim();
  }
  return result;
}

/**
 * Validates an email address format.
 * A happy-path test exists below, but error paths (malformed input,
 * empty string, missing @) are missing — ordinary coverage gaps.
 */
export function validateEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Formats a user's display name from first and last name parts.
 * Has one test below; a missing-middle-name edge case is an ordinary gap.
 */
export function formatDisplayName(first: string, last: string): string {
  return `${first} ${last}`.trim();
}

// -----------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------

// NOTE: parseConfig has NO tests and NO comments suggesting it was ever
// examined defensively. This is an unarmored region, not a coverage gap.

describe('validateEmail', () => {
  // happy path tested — ordinary coverage gap (no negative/boundary tests)
  it('accepts a valid email', () => {
    expect(validateEmail('user@example.com')).toBe(true);
  });

  // missing: empty string, missing @, missing domain, whitespace — coverage gaps
});

describe('formatDisplayName', () => {
  it('formats first and last name', () => {
    expect(formatDisplayName('Ada', 'Lovelace')).toBe('Ada Lovelace');
  });

  // missing: empty strings — ordinary coverage gap
});
