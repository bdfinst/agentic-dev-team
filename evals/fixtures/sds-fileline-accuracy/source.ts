// SKILL: semantic-duplication-scan
// EXPECTED: register entry for calculateTax has line: 7
// NOTE: function definition begins at line 7 (this comment block is lines 1-5, blank line is 6)

// Tax calculation for US domestic orders
function calculateTax(subtotal: number, taxRate: number): number {
  return subtotal * taxRate;
}
