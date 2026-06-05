# Behavior to design tests for

Format a currency amount from an integer number of cents into a display string —
e.g. `1050` → `"$10.50"`, `0` → `"$0.00"`, negative values → `"-$1.00"`.

This is a pure function: no I/O, no user interface, no persistence, no network.
It takes a number and returns a string.
