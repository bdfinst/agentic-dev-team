from money import parse_money, format_money, split
assert split(100,3) == [34,33,33]
assert sum(split(100,3)) == 100
assert split(99,4) == [25,25,25,24]
assert format_money(123456) == "$1,234.56"
print("OK")
