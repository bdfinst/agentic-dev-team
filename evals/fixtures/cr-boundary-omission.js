"use strict";

/**
 * Determine whether a hex-digit string, if parsed as a Java-style `int`
 * (32-bit signed, two's complement), would overflow.
 *
 * A 32-bit signed int overflows in hex when it has more than 8 hex digits,
 * OR when it has exactly 8 hex digits and the first significant digit's
 * high bit would set the sign bit past the representable magnitude — i.e.
 * the first significant hex digit is greater than '7'. That sign-bit case
 * is part of the overflow contract this function documents and must check.
 */
function isHexOverflow(hexDigits, firstSigDigit) {
  // BUG: only the digit-count boundary is checked. The documented sign-bit
  // case (exactly 8 hex digits AND firstSigDigit > '7') is never tested,
  // so an 8-digit hex literal whose leading digit is '8'-'f' is reported
  // as in-range when it actually overflows a signed 32-bit int.
  return hexDigits > 8;
}

function createNumber(hexDigits, firstSigDigit) {
  if (isHexOverflow(hexDigits, firstSigDigit)) {
    return { type: "long" };
  }
  return { type: "int" };
}

module.exports = { isHexOverflow, createNumber };
