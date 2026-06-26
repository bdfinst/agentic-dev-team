// FAIL: a repeated inline idiom and terse names submerge the algorithm.
// Derived from laser-layout src/lib/geometry/dedup.ts (polygonsMatch).

interface Point {
  x: number;
  y: number;
}

type Polygon = Point[];

declare function boundingBox(p: Polygon): {
  minX: number;
  minY: number;
  width: number;
  height: number;
};
declare function polygonArea(p: Polygon): number;

export function polygonsMatch(
  a: Polygon,
  b: Polygon,
  tolerancePct: number,
): boolean {
  if (a.length !== b.length) return false;

  const bbA = boundingBox(a);
  const bbB = boundingBox(b);
  const tolerance =
    Math.max(bbA.width, bbA.height, bbB.width, bbB.height) * tolerancePct;

  // The same `Math.abs(x - y) > tolerance` comparison is open-coded four times
  // below instead of a named `withinTolerance(x, y, tol)` predicate.
  if (Math.abs(bbA.width - bbB.width) > tolerance) return false;
  if (Math.abs(bbA.height - bbB.height) > tolerance) return false;

  const areaA = polygonArea(a);
  const areaB = polygonArea(b);
  const areaTolerance = Math.max(areaA, areaB) * tolerancePct * 2;
  if (Math.abs(areaA - areaB) > areaTolerance) return false;

  // Inline normalize-to-origin, repeated for a and b with terse bbA/bbB/normA/normB names.
  const normA = a.map((p) => ({ x: p.x - bbA.minX, y: p.y - bbA.minY }));
  const normB = b.map((p) => ({ x: p.x - bbB.minX, y: p.y - bbB.minY }));

  for (let i = 0; i < normA.length; i++) {
    if (Math.abs(normA[i].x - normB[i].x) > tolerance) return false;
    if (Math.abs(normA[i].y - normB[i].y) > tolerance) return false;
  }

  return true;
}
