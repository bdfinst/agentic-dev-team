from roman import to_roman, from_roman
assert from_roman("IV") == 4
assert from_roman("MCMXCIV") == 1994
for n in (1,4,9,58,1994,3999):
    assert from_roman(to_roman(n)) == n, n
print("OK from_roman")
