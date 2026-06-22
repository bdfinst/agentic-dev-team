from money import parse_money, format_money
assert parse_money("$1,234.56") == 123456
assert parse_money("$0.00") == 0
assert parse_money("$12.05") == 1205
assert format_money(123456) == "$1,234.56"
assert format_money(0) == "$0.00"
assert format_money(1205) == "$12.05"
print("OK")
