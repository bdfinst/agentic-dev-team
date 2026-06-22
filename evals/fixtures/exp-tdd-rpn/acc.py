from rpn import evaluate
assert evaluate("3 4 +") == 7
assert evaluate("2 3 *") == 6
assert evaluate("6 2 /") == 3
assert evaluate("5 1 2 + 4 * + 3 -") == 14
print("OK")
