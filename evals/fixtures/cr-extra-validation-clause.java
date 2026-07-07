/**
 * Numeric-literal helpers for a lightweight number parser.
 */
public final class NumberValidator {

    /**
     * True when every character in `digits` is the zero digit '0' — used to
     * detect a value that is numerically zero regardless of its decimal or
     * exponent parts (e.g. "0", "0.0", "0.00e0" are all "all zeros").
     * Callers must pass BOTH the integer part and the decimal part
     * concatenated, since a value like "0.5" is not all zeros even though
     * its integer part is.
     */
    private static boolean isAllZeros(String intPart, String decPart) {
        String digits = intPart + decPart;
        for (int i = 0; i < digits.length(); i++) {
            if (digits.charAt(i) != '0') {
                return false;
            }
        }
        return true;
    }

    public static boolean isEffectivelyZero(String intPart, String decPart) {
        // BUG (decoy -- a different, real defect): isAllZeros() is documented
        // as requiring BOTH intPart and decPart, but decPart is silently
        // dropped here (an empty string is passed instead), so "0.5" is
        // wrongly reported as zero.
        return isAllZeros(intPart, "");
    }

    /**
     * Checks whether the trailing character of a numeric literal is
     * acceptable. A trailing decimal point (e.g. "123.") is never a valid
     * ending for a numeric literal -- only a trailing digit is acceptable.
     */
    public static boolean hasValidTrailingChar(char[] chars) {
        char lastChar = chars[chars.length - 1];
        // BUG (target -- Defects4J Lang-36 shape): the docstring above states a
        // trailing decimal point is NEVER acceptable, but this condition
        // adds `&& lastChar != '.'`, which *exempts* a trailing '.' from
        // rejection -- directly contradicting the stated rule and letting
        // a value like "123." pass validation.
        if (!Character.isDigit(lastChar) && lastChar != '.') {
            return false;
        }
        return true;
    }
}
