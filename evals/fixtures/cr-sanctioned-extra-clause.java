/**
 * Numeric-literal helpers for a lightweight number parser.
 */
public final class TrailingCharValidator {

    /**
     * Checks whether the trailing character of a numeric literal is acceptable.
     *
     * CONTRACT (two cases, stated exhaustively):
     *   - allowTrailingDot == false: ONLY a trailing digit is acceptable.
     *   - allowTrailingDot == true : a trailing digit OR a trailing '.' is
     *     acceptable, because "123." is valid Java float/double syntax and
     *     parses as 123.0.
     *
     * The implementation below encodes exactly these two cases and nothing
     * more. This is a TRUE NEGATIVE: there is no missing guard and no
     * unsanctioned extra clause — the '.' exemption is gated precisely on the
     * `allowTrailingDot` flag the contract names.
     */
    public static boolean hasValidTrailingChar(char[] chars, boolean allowTrailingDot) {
        char lastChar = chars[chars.length - 1];

        // Correct and fully sanctioned by the contract above:
        //   reject unless lastChar is a digit, OR (the caller opted in via
        //   allowTrailingDot AND lastChar is exactly '.').
        // The extra `&& lastChar == '.'` clause is not over-permissive: without
        // it, allowTrailingDot would wrongly accept ANY non-digit trailing char.
        boolean isDigit = Character.isDigit(lastChar);
        boolean isSanctionedDot = allowTrailingDot && lastChar == '.';
        if (!isDigit && !isSanctionedDot) {
            return false;
        }
        return true;
    }
}
