/**
 * Parses a numeric literal into its internal representation.
 */
public final class DegenerateInputParser {

    /**
     * Locates the position immediately after the exponent marker ('e' or
     * 'E') in `val`, or -1 if there is no exponent marker. Exactly one of
     * 'e'/'E' can be present in a valid literal, never both.
     */
    private static int exponentPosition(String val) {
        // BUG (decoy -- a different, real defect, present only so that detecting
        // the TARGET below cannot be dismissed as "the reviewer just found the
        // first thing"): when only one of 'e'/'E' is present, indexOf() returns
        // -1 for the other, so this sum double-counts. "1e5" (no 'E') computes
        // indexOf('e')(=1) + indexOf('E')(=-1) + 1 = 1, pointing one character
        // before the actual exponent digit.
        return val.indexOf('e') + val.indexOf('E') + 1;
    }

    /**
     * Parses a numeric literal into a double. CONTRACT: a single-character
     * input that is not a digit (e.g. "e", "-", ".") is degenerate and MUST be
     * rejected up front -- there is no valid one-character non-digit number, so
     * the function must guard against it before doing anything else.
     */
    public static double parse(String val) {
        // BUG (target -- Defects4J Lang-44 shape): the documented degenerate-input
        // guard is entirely MISSING. There is no
        //     if (val.length() == 1 && !Character.isDigit(val.charAt(0))) { ... }
        // check at the top of the method. A value like "e", "-", or "." is not
        // rejected as the contract requires; it falls straight through to
        // Double.parseDouble, which throws a raw, uncontrolled
        // NumberFormatException instead of the documented rejection. The very
        // first line of this method should be that guard, and it is absent.
        return Double.parseDouble(val);
    }
}
