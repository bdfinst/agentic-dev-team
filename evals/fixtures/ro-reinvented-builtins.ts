// FAIL: hand-rolls a standard-library built-in and re-implements an existing
// in-module helper inline. Two clear reinvent-the-platform refactor
// opportunities (suggestions, not errors — the manual loop could be an
// intentional single-pass optimization, so the reviewer flags, not mandates).
// Derived from laser-layout src/lib/geometry/polygon.ts.

interface Point {
  x: number;
  y: number;
}

type Polygon = Point[];

// Reinvents Math.min / Math.max: a manual min/max scan over each axis, exactly
// what `Math.min(...xs)` / `Math.max(...xs)` express in one line each.
export function boundingBox(polygon: Polygon) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of polygon) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
}

// This helper already exists in the module...
export function translatePolygon(
  polygon: Polygon,
  dx: number,
  dy: number,
): Polygon {
  return polygon.map((p) => ({ x: p.x + dx, y: p.y + dy }));
}

// ...but shiftToOrigin re-implements translatePolygon's body inline instead of
// calling `translatePolygon(polygon, -bb.minX, -bb.minY)`.
export function shiftToOrigin(polygon: Polygon): Polygon {
  const bb = boundingBox(polygon);
  return polygon.map((p) => ({ x: p.x - bb.minX, y: p.y - bb.minY }));
}
