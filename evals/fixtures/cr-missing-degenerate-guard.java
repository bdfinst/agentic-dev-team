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
        // BUG (decoy -- a different, real defect): when only one of 'e'/'E'
        // is present, indexOf() returns -1 for the other, so this sum
        // double-counts and returns the wrong position (e.g. "1e5" with no
        // 'E' present computes indexOf('e')(=1) + indexOf('E')(=-1) + 1 = 1,
        // silently pointing one character before the actual exponent digit).
        return val.indexOf('e') + val.indexOf('E') + 1;
    }

    /**
     * Parses a numeric literal into a double. A single-character input that
     * is not a digit (e.g. "e", "-", ".") is degenerate and must be
     * rejected before any further parsing is attempted -- there is no valid
     * one-character non-digit number.
     */
    public static double parse(String val) {
        // BUG (target -- Defects4J Lang-44 shape): the docstring above requires
        // rejecting a single-character, non-digit input before parsing
        // proceeds, but no such guard exists here -- a value like "e" or
        // "." falls straight through to Double.parseDouble, which throws a
        // raw, uncontrolled NumberFormatException instead of the documented
        // rejection.
        return Double.parseDouble(val);
    }
}
