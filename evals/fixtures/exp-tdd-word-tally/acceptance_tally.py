from tally import word_count
assert word_count("") == {}, word_count("")
assert word_count("Hello hello HELLO") == {"hello": 3}
assert word_count("The cat, the hat; the CAT!") == {"the": 3, "cat": 2, "hat": 1}
assert word_count("a1b2c") == {"a": 1, "b": 1, "c": 1}
print("OK word_count")
