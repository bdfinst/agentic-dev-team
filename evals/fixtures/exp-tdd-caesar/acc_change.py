from caesar import encrypt, decrypt
assert decrypt("bcd", 1) == "abc"
assert decrypt("Mjqqt, Btwqi!", 5) == "Hello, World!"
for shift in (0, 1, 5, 13, 25):
    assert decrypt(encrypt("Hello, World!", shift), shift) == "Hello, World!"
print("OK")
