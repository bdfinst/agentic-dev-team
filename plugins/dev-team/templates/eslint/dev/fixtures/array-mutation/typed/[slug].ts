// The file name holds glob metacharacters; the typed file list must still match it.
export function route(ids: string[]): void {
  ids.push("x");
}
