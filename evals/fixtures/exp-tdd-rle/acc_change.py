from rle import encode, decode
assert decode("a3b2c1") == "aaabbc"
assert decode("") == ""
for s in ("", "a", "aaabbc", "wwwwww", "xyz", "a"*12):
    assert decode(encode(s)) == s
print("OK")
