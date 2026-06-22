from caesar import encrypt
assert encrypt("abc", 1) == "bcd"
assert encrypt("xyz", 3) == "abc"
assert encrypt("Hello, World!", 5) == "Mjqqt, Btwqi!"
assert encrypt("abc", 0) == "abc"
print("OK")
