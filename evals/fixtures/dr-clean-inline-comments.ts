// PASS: comments explain intent and behavior without leaking tracker IDs,
// and each doc comment sits directly above the symbol it describes.
// Clean counterpart to dr-tracker-ids-in-comments.ts.

export interface NestingConfig {
  sheet: { width: number; height: number };
  kerf: number;

  /**
   * Opt-in NFP-based placement: exact-phase candidate seats and NFP-clearance
   * collision. Off by default — denser, but ~3–4x slower pending tuning.
   */
  useNfpPlacement?: boolean;

  /** Mild fitness pull toward a clustered pack; undefined ⇒ optimizer default. */
  gravityWeight?: number;

  /** Mild fitness pull toward one large reusable offcut; 0 disables the term. */
  remnantWeight?: number;

  /**
   * When true, parts may abut (clearance drops to 0) and the fitness rewards
   * coincident shared edges so adjacent parts share a single cut line.
   */
  commonLineCutting?: boolean;
}

/** Default spacing between parts, in millimetres. */
export const DEFAULT_KERF = 1;
