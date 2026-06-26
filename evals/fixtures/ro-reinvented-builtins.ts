// FAIL: hand-rolls language/standard-library built-ins and an existing helper.
// Derived from laser-layout src/lib/geometry/polygon.ts (boundingBox, reflectPolygon).

interface Point {
  x: number;
  y: number;
}

type Polygon = Point[];

// Reinvents Math.min / Math.max with a manual scan.
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

// `translatePolygon` already exists in this module, but the call site below
// re-implements its body inline instead of calling it.
export function translatePolygon(
  polygon: Polygon,
  dx: number,
  dy: number,
): Polygon {
  return polygon.map((p) => ({ x: p.x + dx, y: p.y + dy }));
}

export function shiftToOrigin(polygon: Polygon): Polygon {
  const bb = boundingBox(polygon);
  // Duplicates translatePolygon(polygon, -bb.minX, -bb.minY).
  return polygon.map((p) => ({ x: p.x - bb.minX, y: p.y - bb.minY }));
}

// `0 - p.x` instead of the unary-minus idiom `-p.x`.
export function reflectPolygon(polygon: Polygon): Polygon {
  return polygon.map((p) => ({ x: 0 - p.x, y: p.y }));
}
