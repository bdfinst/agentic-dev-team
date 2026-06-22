from tally import word_count, top_n
assert word_count("the the cat") == {"the": 2, "cat": 1}   # regression
assert top_n("a a b b b c", 2) == [("b", 3), ("a", 2)]
assert top_n("x x y y z", 2) == [("x", 2), ("y", 2)]       # tie -> alpha asc
assert top_n("", 3) == []
print("OK top_n")
