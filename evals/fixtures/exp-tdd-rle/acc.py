from rle import encode
assert encode("") == ""
assert encode("a") == "a1"
assert encode("aaabbc") == "a3b2c1"
assert encode("wwwwww") == "w6"
print("OK")
