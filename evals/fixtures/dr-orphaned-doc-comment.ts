// FAIL: a doc comment is detached from the function it describes.
// Derived from laser-layout src/lib/geometry/polygon.ts (the rigid-body block
// that ended up sitting above reflectPolygon instead of transformPartPolygons).

interface Point {
  x: number;
  y: number;
}

type Polygon = Point[];

/**
 * Transform a part's polygons as a single rigid body: rotate every polygon
 * around the outer boundary's centroid, then translate the whole group so the
 * outer boundary's bounding box sits at (x, y). `polygons[0]` is the outer
 * boundary; the rest are cutouts.
 */
// The block above describes transformPartPolygons (below), not reflectPolygon.
export function reflectPolygon(polygon: Polygon): Polygon {
  return polygon.map((p) => ({ x: -p.x, y: p.y }));
}

export function transformPartPolygons(polygons: Polygon[]): Polygon[] {
  // ... rotates around centroid and translates the group ...
  return polygons;
}
