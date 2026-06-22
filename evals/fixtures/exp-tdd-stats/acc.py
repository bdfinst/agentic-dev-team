from stats import mean, median, variance
assert mean([1,2,3,4]) == 2.5
assert median([1,2,3]) == 2
assert median([1,2,3,4]) == 2.5
assert variance([2,2,2]) == 0
assert abs(variance([1,2,3,4,5]) - 2.0) < 1e-9
print("OK")
