/**
 * Generated fast-check property test — round-trip property for
 * encode/decode. Shape documented in
 * ../../references/languages/javascript.md; do not hand-edit, regenerate if
 * roundtrip.js changes.
 */
import { describe, it } from 'vitest';
import fc from 'fast-check';

import { encode, decode } from './roundtrip.js';

describe('encode/decode round-trip property', () => {
  it('decode(encode(x)) === x for any string', () => {
    fc.assert(fc.property(fc.string(), (x) => decode(encode(x)) === x));
  });
});
