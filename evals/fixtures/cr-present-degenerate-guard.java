/**
 * Parses a numeric literal into its internal representation.
 */
public final class DegenerateInputParser {

    /**
     * Parses a numeric literal into a double. A single-character input that
     * is not a digit (e.g. "e", "-", ".") is degenerate and must be
     * rejected before any further parsing is attempted -- there is no valid
     * one-character non-digit number.
     */
    public static double parse(String val) {
        // Not a bug: the guard the docstring above requires is present,
        // right at function entry, before the underlying parser ever sees
        // a degenerate single-character input.
        if (val.length() == 1 && !Character.isDigit(val.charAt(0))) {
            throw new NumberFormatException(val + " is not a valid number.");
        }
        return Double.parseDouble(val);
    }
}
