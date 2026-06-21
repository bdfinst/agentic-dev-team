# Change: add day support
Extend both functions to support a `d` (days) unit, larger than hours, so
parse_duration("1d2h") == 93600 and format_duration(86400) == "1d". Round-trip
must hold. Existing h/m/s behavior must not change.
