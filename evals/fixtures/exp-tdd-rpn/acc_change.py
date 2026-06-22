from rpn import evaluate
assert evaluate("2 3 ^") == 8
assert evaluate("2 1 2 + ^") == 8
assert evaluate("3 4 +") == 7   # regression
print("OK")
