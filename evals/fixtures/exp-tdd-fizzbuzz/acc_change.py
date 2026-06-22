from fizzbuzz import fizzbuzz
r = fizzbuzz(105)
assert r[6] == "Bazz" and r[20] == "FizzBazz"
assert r[34] == "BuzzBazz" and r[104] == "FizzBuzzBazz"
assert r[2] == "Fizz" and r[14] == "FizzBuzz"   # regression
print("OK")
