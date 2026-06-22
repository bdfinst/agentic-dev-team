from timeparse import parse_duration, format_duration
assert parse_duration("45s") == 45
assert parse_duration("1h30m") == 5400
assert parse_duration("1m30s") == 90
assert format_duration(5400) == "1h30m"
assert format_duration(90) == "1m30s"
assert format_duration(45) == "45s"
assert format_duration(0) == "0s"
print("OK")
