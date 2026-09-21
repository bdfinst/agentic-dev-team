/**
 * Fixture module for the fast-check round-trip property path (#2190).
 *
 * Exposes `encode`/`decode` as named exports — the same literal-name
 * round-trip heuristic `hypothesis_scaffold.py`'s Python path looks for
 * (see `../roundtrip_fixture.py`), mirrored here for the JS/TS path
 * documented in `../../references/languages/javascript.md`.
 *
 * `decode(encode(value)) === value` holds for any string because reversal
 * is its own inverse.
 */

/**
 * Encode a string by reversing it.
 * @param {string} value
 * @returns {string}
 */
export function encode(value) {
  return [...value].reverse().join('');
}

/**
 * Decode a string produced by encode() by reversing it back.
 * @param {string} value
 * @returns {string}
 */
export function decode(value) {
  return [...value].reverse().join('');
}
