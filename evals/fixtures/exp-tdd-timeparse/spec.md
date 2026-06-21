# Feature: durations (timeparse.py)
Implement in `timeparse.py`:
- `parse_duration(s)` — parse a string like "1h30m", "45s", "1m30s" into total
  seconds (units h, m, s).
- `format_duration(secs)` — inverse: render seconds using h/m/s, omitting any
  zero component; 0 renders as "0s". e.g. 5400 -> "1h30m", 90 -> "1m30s".
