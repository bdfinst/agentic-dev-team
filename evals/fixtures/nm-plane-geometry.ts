const DEGREES_PER_HALF_TURN = 180;

interface Point {
  readonly x: number;
  readonly y: number;
}

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / DEGREES_PER_HALF_TURN;
}

function distance(from: Point, to: Point): number {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  return Math.hypot(dx, dy);
}

function centroid(points: readonly Point[]): Point {
  let sumX = 0;
  let sumY = 0;
  for (let i = 0; i < points.length; i++) {
    sumX += points[i].x;
    sumY += points[i].y;
  }
  return { x: sumX / points.length, y: sumY / points.length };
}

function rotateAround(point: Point, pivot: Point, angleDegrees: number): Point {
  const angleRadians = toRadians(angleDegrees);
  const cos = Math.cos(angleRadians);
  const sin = Math.sin(angleRadians);
  const dx = point.x - pivot.x;
  const dy = point.y - pivot.y;
  return {
    x: pivot.x + dx * cos - dy * sin,
    y: pivot.y + dx * sin + dy * cos,
  };
}

function perimeter(polygon: readonly Point[]): number {
  let total = 0;
  for (let i = 0; i < polygon.length; i++) {
    const next = polygon[(i + 1) % polygon.length];
    total += distance(polygon[i], next);
  }
  return total;
}

function boundingBoxWidth(points: readonly Point[]): number {
  const xs = points.map((p) => p.x);
  return Math.max(...xs) - Math.min(...xs);
}

export {
  toRadians,
  distance,
  centroid,
  rotateAround,
  perimeter,
  boundingBoxWidth,
};
