from jsonptr import (
    parse,
    resolve,
    resolve_default,
    apply_patch,
    PointerError,
    ResolveError,
    PatchError,
)

# --- Change: move op ---
assert apply_patch(
    {"a": 1, "b": {}}, [{"op": "move", "from": "/a", "path": "/b/x"}]
) == {"b": {"x": 1}}

# move within an array (insert semantics at destination)
assert apply_patch(
    {"a": [1, 2, 3]}, [{"op": "move", "from": "/a/0", "path": "/a/-"}]
) == {"a": [2, 3, 1]}

# --- Change: copy op (source stays in place) ---
assert apply_patch(
    {"a": 1, "b": {}}, [{"op": "copy", "from": "/a", "path": "/b/x"}]
) == {"a": 1, "b": {"x": 1}}

# --- Change: lenient object remove (missing key is a no-op) ---
assert apply_patch({"a": 1}, [{"op": "remove", "path": "/zzz"}]) == {"a": 1}

# --- Change: bad array index remove still raises ---
try:
    apply_patch({"a": [1, 2]}, [{"op": "remove", "path": "/a/5"}])
    assert False, "expected PatchError for out-of-range array remove"
except PatchError:
    pass

# --- Change: resolve_default returns default on a miss ---
assert resolve_default({"a": {"b": 7}}, "/a/x", "DEF") == "DEF"
assert resolve_default({"a": [1, 2]}, "/a/9", -1) == -1
assert resolve_default({"a": {"b": 7}}, "/a/b", "DEF") == 7
# syntactically invalid pointer still raises
try:
    resolve_default({"a": 1}, "nope", None)
    assert False, "expected PointerError"
except PointerError:
    pass

# non-mutation still holds for move/copy
orig = {"a": 1, "b": {"c": 3}}
apply_patch(orig, [{"op": "move", "from": "/a", "path": "/b/x"}])
assert orig == {"a": 1, "b": {"c": 3}}, "move mutated input"

# === Regression: Stage-1 behavior unchanged ===
assert parse("/a~1b/c~0d") == ["a/b", "c~d"]
assert resolve({"a": [10, 20, 30]}, "/a/2") == 30
assert apply_patch({"a": 1}, [{"op": "add", "path": "/b", "value": 2}]) == {
    "a": 1,
    "b": 2,
}
assert apply_patch({"a": 1}, [{"op": "replace", "path": "/a", "value": 9}]) == {"a": 9}
# replace on missing key still raises (NOT made lenient)
try:
    apply_patch({"a": 1}, [{"op": "replace", "path": "/zzz", "value": 9}])
    assert False, "expected PatchError for replace on missing key"
except PatchError:
    pass
# resolve still raises on a miss (unchanged)
try:
    resolve({"a": {"b": 7}}, "/a/x")
    assert False, "expected ResolveError"
except ResolveError:
    pass

print("OK")
