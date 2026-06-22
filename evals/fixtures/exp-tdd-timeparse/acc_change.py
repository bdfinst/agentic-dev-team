from timeparse import parse_duration, format_duration
assert parse_duration("1d2h") == 93600
assert format_duration(86400) == "1d"
assert parse_duration("1h30m") == 5400
for s in (45,90,5400,86400,93600):
    assert parse_duration(format_duration(s)) == s
print("OK")
