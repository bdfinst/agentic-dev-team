// FAIL: issue-tracker / epic IDs bleed into shipped code comments.
// Derived from laser-layout src/lib/geometry/types.ts (NestingConfig).

export interface NestingConfig {
  sheet: { width: number; height: number };
  kerf: number;

  // Opt-in NFP-based placement (epic #24, P3–P5): exact-phase candidate seats.
  // Off by default — the path is ~3–4x slower and not yet a net bench win.
  useNfpPlacement?: boolean;

  // Remnant-aware fitness weights (#41): a mild pull toward a clustered pack.
  gravityWeight?: number;
  remnantWeight?: number;

  // Common-line cutting (#43): when true, parts are allowed to abut so adjacent
  // parts share a single cut line.
  commonLineCutting?: boolean;
}

// See JIRA-1187 for the rationale behind this default.
export const DEFAULT_KERF = 1;
