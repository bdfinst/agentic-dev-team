// FAIL: a doc comment is detached from the function it describes.
// Derived from laser-layout src/lib/geometry/polygon.ts (the rigid-body block
// that ended up sitting above reflectPolygon instead of transformPartPolygons).

interface Point {
  x: number;
  y: number;
}

type Polygon = Point[];

/**
 * Transform a part's polygons as a single rigid body: ROTATE every polygon
 * around the outer boundary's centroid, then TRANSLATE the whole group so the
 * outer boundary's bounding box sits at (x, y). `polygons[0]` is the outer
 * boundary; the rest are cutouts. Takes a `Polygon[]` and an (x, y) target.
 */
// MISMATCH: the JSDoc block directly above documents transformPartPolygons —
// rotation, translation, a Polygon[] group, an (x, y) target. But it is
// attached to reflectPolygon, which does none of that: it takes a single
// Polygon and only mirrors x. The doc comment describes the wrong function.
export function reflectPolygon(polygon: Polygon): Polygon {
  return polygon.map((p) => ({ x: -p.x, y: p.y }));
}

// The function the block above actually describes — and which has no doc
// comment of its own.
export function transformPartPolygons(polygons: Polygon[]): Polygon[] {
  // ... rotates around centroid and translates the group ...
  return polygons;
}
