// SKILL: semantic-duplication-scan
// EXPECTED: register entry with all required fields including promptVersion
// EXPECTED FIELDS: file, function, layer, semanticDescription.verb,
//   semanticDescription.domainConcept, semanticDescription.inputs,
//   semanticDescription.outputConcept, promptVersion, commitHash, line

// Non-trivial: arithmetic computation, no external imports → layer: domain
function applyDiscount(basePrice: number, discountRate: number): number {
  return basePrice * (1 - discountRate);
}
