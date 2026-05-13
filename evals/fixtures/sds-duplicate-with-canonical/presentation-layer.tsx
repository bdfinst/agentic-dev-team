// SKILL: semantic-duplication-scan
// LAYER: presentation (expected)
// ROLE: leaked duplicate — imports React (presentation coupling)
// EXPECTED: flagged as duplicate of domain-layer.ts::applyDiscount
// EXPECTED canonical: domain-layer.ts::applyDiscount
// EXPECTED output: "canonical: suggested domain-layer.ts:5 — requires human confirmation"

import React from "react";

interface PriceDisplayProps {
  basePrice: number;
  salePercent: number;
}

function PriceDisplay({ basePrice, salePercent }: PriceDisplayProps): React.ReactNode {
  // Same business rule as applyDiscount — reimplemented in presentation layer
  const discountedPrice = basePrice * (1 - salePercent / 100);
  return <span className="sale-price">${discountedPrice.toFixed(2)}</span>;
}
