from jsonptr import (
    parse,
    resolve,
    apply_patch,
    PointerError,
    ResolveError,
    PatchError,
)

# 1. parse simple
assert parse("/foo/bar") == ["foo", "bar"]

# 2. parse with ~0 / ~1 escaping
assert parse("/a~1b/c~0d") == ["a/b", "c~d"]
assert parse("/~01") == ["~1"]

# 3. parse "" -> []
assert parse("") == []

# 4. parse non-empty without leading "/" -> PointerError
try:
    parse("foo")
    assert False, "expected PointerError"
except PointerError:
    pass

# 5. resolve nested object
assert resolve({"a": {"b": 7}}, "/a/b") == 7

# 6. resolve array index
assert resolve({"a": [10, 20, 30]}, "/a/2") == 30

# "" resolves to whole doc
d0 = {"x": 1}
assert resolve(d0, "") is d0

# 7. resolve missing key -> ResolveError
try:
    resolve({"a": {"b": 7}}, "/a/x")
    assert False, "expected ResolveError"
except ResolveError:
    pass

# out-of-range array index -> ResolveError
try:
    resolve({"a": [1, 2]}, "/a/5")
    assert False, "expected ResolveError"
except ResolveError:
    pass

# non-decimal token against a list -> ResolveError
try:
    resolve({"a": [1, 2]}, "/a/x")
    assert False, "expected ResolveError"
except ResolveError:
    pass

# 8. patch add to object
assert apply_patch({"a": 1}, [{"op": "add", "path": "/b", "value": 2}]) == {
    "a": 1,
    "b": 2,
}

# 9. patch add append "-" and insert at index
assert apply_patch({"a": [1, 2]}, [{"op": "add", "path": "/a/-", "value": 3}]) == {
    "a": [1, 2, 3]
}
assert apply_patch({"a": [1, 2]}, [{"op": "add", "path": "/a/1", "value": 9}]) == {
    "a": [1, 9, 2]
}

# 10. patch remove + out-of-range array index raises
assert apply_patch({"a": 1, "b": 2}, [{"op": "remove", "path": "/a"}]) == {"b": 2}
try:
    apply_patch({"a": [1, 2]}, [{"op": "remove", "path": "/a/5"}])
    assert False, "expected PatchError"
except PatchError:
    pass

# 11. patch replace + missing key raises
assert apply_patch({"a": 1}, [{"op": "replace", "path": "/a", "value": 9}]) == {"a": 9}
try:
    apply_patch({"a": 1}, [{"op": "replace", "path": "/zzz", "value": 9}])
    assert False, "expected PatchError"
except PatchError:
    pass

# 12. non-mutation of input
orig = {"a": [1, 2], "b": {"c": 3}}
result = apply_patch(
    orig,
    [
        {"op": "add", "path": "/a/-", "value": 99},
        {"op": "replace", "path": "/b/c", "value": 100},
    ],
)
assert orig == {"a": [1, 2], "b": {"c": 3}}, "input doc was mutated"
assert result == {"a": [1, 2, 99], "b": {"c": 100}}

# 13. unknown op -> PatchError
try:
    apply_patch({"a": 1}, [{"op": "frobnicate", "path": "/a", "value": 0}])
    assert False, "expected PatchError"
except PatchError:
    pass

print("OK")
