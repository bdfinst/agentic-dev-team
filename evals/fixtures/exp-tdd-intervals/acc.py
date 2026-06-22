from intervals import merge
assert merge([]) == []
assert merge([(1,3)]) == [(1,3)]
assert merge([(1,3),(2,6),(8,10)]) == [(1,6),(8,10)]
assert merge([(8,10),(1,3),(2,6)]) == [(1,6),(8,10)]
assert merge([(1,4),(4,5)]) == [(1,5)]
print("OK")
