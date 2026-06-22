from roman import to_roman
for n, s in [(1,"I"),(4,"IV"),(9,"IX"),(58,"LVIII"),(1994,"MCMXCIV"),(3999,"MMMCMXCIX")]:
    assert to_roman(n) == s, (n, to_roman(n))
for bad in (0, 4000, -1):
    try:
        to_roman(bad); raise AssertionError("expected ValueError for %r" % bad)
    except ValueError:
        pass
print("OK to_roman")
