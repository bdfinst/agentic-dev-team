// SKILL: semantic-duplication-scan
// EXPECTED layer: "unknown"
// REASON: imports a custom utility with no clear infrastructure or presentation coupling

import { formatValue } from "./internal-utils";

function processMetric(raw: number, scale: number): string {
  const scaled = raw * scale;
  return formatValue(scaled);
}
