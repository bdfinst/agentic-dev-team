// ORACLE PROVENANCE — CIRCULAR: all expected values captured from system output.
// No external specification, hand calculation, or reference implementation.
// Expected: circular-oracle-dominated warning/error, quality cap at 60.

import { describe, it, expect } from 'vitest';

// System under test — a simple formatter
function formatCurrency(amount: number, currency: string): string {
  return `${currency} ${amount.toFixed(2)}`;
}

function summarizeItems(items: string[]): string {
  return items.join(', ');
}

describe('formatCurrency', () => {
  // CIRCULAR: expected value was recorded from the system's first run.
  // There is no spec comment, formula, or external derivation.
  it('formats a dollar amount', () => {
    expect(formatCurrency(42, 'USD')).toMatchSnapshot();
  });

  // CIRCULAR: inline snapshot — expected value is the system's own prior output.
  it('formats a euro amount', () => {
    expect(formatCurrency(9.9, 'EUR')).toMatchInlineSnapshot(`"EUR 9.90"`);
  });

  // CIRCULAR: assertion copied from a baseline run log with no verification.
  // baseline captured: "GBP 0.00"
  it('formats zero', () => {
    expect(formatCurrency(0, 'GBP')).toBe('GBP 0.00');
  });
});

describe('summarizeItems', () => {
  // CIRCULAR: snapshot with no external justification.
  it('joins items', () => {
    expect(summarizeItems(['a', 'b', 'c'])).toMatchSnapshot();
  });

  // CIRCULAR: empty-list snapshot — baseline captured from first run.
  it('handles empty list', () => {
    expect(summarizeItems([])).toMatchInlineSnapshot(`""`);
  });
});
