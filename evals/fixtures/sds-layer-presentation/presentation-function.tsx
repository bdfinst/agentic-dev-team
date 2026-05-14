// SKILL: semantic-duplication-scan
// EXPECTED layer: "presentation"
// REASON: imports React component — rendering/display coupling

import React from "react";

function formatCurrencyDisplay(amount: number, currency: string): React.ReactNode {
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(amount);
  return <span className="price">{formatted}</span>;
}
