// PASS: uses built-ins and the existing helper; the algorithm reads top-down.
// Clean counterpart to ro-reinvented-builtins.ts.

interface Point {
  x: number;
  y: number;
}

type Polygon = Point[];

export function boundingBox(polygon: Polygon) {
  const xs = polygon.map((p) => p.x);
  const ys = polygon.map((p) => p.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
}

export function translatePolygon(
  polygon: Polygon,
  dx: number,
  dy: number,
): Polygon {
  return polygon.map((p) => ({ x: p.x + dx, y: p.y + dy }));
}

export function shiftToOrigin(polygon: Polygon): Polygon {
  const { minX, minY } = boundingBox(polygon);
  return translatePolygon(polygon, -minX, -minY);
}

export function reflectPolygon(polygon: Polygon): Polygon {
  return polygon.map((p) => ({ x: -p.x, y: p.y }));
}
