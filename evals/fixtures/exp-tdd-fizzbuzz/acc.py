from fizzbuzz import fizzbuzz
r = fizzbuzz(15)
assert len(r) == 15
assert r[0] == "1" and r[1] == "2"
assert r[2] == "Fizz" and r[4] == "Buzz" and r[14] == "FizzBuzz"
print("OK")
