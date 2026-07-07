/**
 * Numeric-literal helpers for a lightweight number parser.
 */
public final class TrailingCharValidator {

    /**
     * Checks whether the trailing character of a numeric literal is
     * acceptable. A trailing decimal point (e.g. "123.") IS a valid ending
     * when the caller has flagged this literal as float-typed
     * (`allowTrailingDot`), since a trailing '.' with no fractional digits
     * is valid Java float/double syntax in that mode (e.g. "123." parses as
     * 123.0). When `allowTrailingDot` is false, only a trailing digit is
     * acceptable.
     */
    public static boolean hasValidTrailingChar(char[] chars, boolean allowTrailingDot) {
        char lastChar = chars[chars.length - 1];
        // Not a bug: the extra clause is exactly the case the docstring
        // above sanctions -- a trailing '.' is only exempted from
        // rejection when the caller explicitly opted in via
        // `allowTrailingDot`, matching the stated rule precisely.
        if (!Character.isDigit(lastChar) && !(allowTrailingDot && lastChar == '.')) {
            return false;
        }
        return true;
    }
}
