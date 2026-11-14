# Task: parse human-readable durations

Add `parse_duration(text: str) -> int` to `timekit/duration.py`. It returns the
number of seconds in a duration written as one or more `<integer><unit>` parts.

Acceptance criteria:

1. Units are `h` (hours), `m` (minutes) and `s` (seconds): `"1h30m"` is 5400,
   `"45s"` is 45, `"2h"` is 7200.
2. Parts appear in the order h, m, s, each at most once: `"1h2m3s"` is 3723.
3. Surrounding whitespace is ignored: `" 10m "` is 600.
4. Anything else raises `ValueError`: an empty string, an unknown unit (`"5d"`),
   a part with no number (`"h"`), parts out of order (`"5m1h"`), or a repeated
   unit (`"1m1m"`).

`tests/test_acceptance.py` encodes these criteria and must pass unchanged.
