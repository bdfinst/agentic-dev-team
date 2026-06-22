from intervals import merge, total_covered
assert total_covered([(1,3),(2,6),(8,10)]) == 7
assert total_covered([]) == 0
assert total_covered([(1,4),(4,5)]) == 4
assert merge([(1,3),(2,6),(8,10)]) == [(1,6),(8,10)]
print("OK")
