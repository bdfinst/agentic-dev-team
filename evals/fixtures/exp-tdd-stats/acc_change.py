from stats import mean, median, variance, mode, data_range
assert mode([1,2,2,3,3,3]) == 3
assert mode([4,4,5,5]) == 4
assert data_range([3,7,2,9]) == 7
assert mean([1,2,3,4]) == 2.5
assert variance([2,2,2]) == 0
print("OK")
