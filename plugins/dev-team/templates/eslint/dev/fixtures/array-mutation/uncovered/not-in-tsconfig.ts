// Not covered by the fixture tsconfig, so the typed rule must not run here.
export function notInProject(xs: number[]): void {
  xs.push(1);
}
