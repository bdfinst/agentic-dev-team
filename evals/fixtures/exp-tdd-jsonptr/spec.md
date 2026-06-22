# Feature: JSON Pointer + JSON Patch (`jsonptr` package)

Implement a JSON Pointer (RFC 6901) and JSON Patch (subset of RFC 6902) library.
The public API is re-exported from `jsonptr/__init__.py`, so `import jsonptr`
exposes every name below. Implementation lives across two modules.

Define and export three exception types: `PointerError`, `ResolveError`,
`PatchError`.

## `jsonptr/pointer.py`

### `parse(pointer: str) -> list[str]`
Parse a JSON Pointer string into its reference tokens.
- The empty string `""` returns `[]` (addresses the whole document).
- `"/foo/0/bar"` returns `["foo", "0", "bar"]`.
- Tokens are decoded: `~1` becomes `/` and `~0` becomes `~`. The `~1` decoding
  is applied before `~0` per RFC 6901, so `"~01"` decodes to `"~1"`.
- A non-empty pointer that does **not** start with `"/"` raises `PointerError`.

### `resolve(doc, pointer: str)`
Return the value addressed by `pointer` inside `doc`.
- `""` returns the whole `doc` (the same object passed in).
- For an object (dict) token, the token is the key. A missing key raises
  `ResolveError`.
- For an array (list) token, the token must be a decimal index (`"0"`, `"12"`).
  An out-of-range index raises `ResolveError`. A non-decimal token against a
  list (e.g. `"x"`) raises `ResolveError`.
- Resolving into a non-container (e.g. an int) raises `ResolveError`.

## `jsonptr/patch.py`

### `apply_patch(doc, ops: list[dict]) -> new_doc`
Apply an ordered list of patch operations and return a **new** document. The
input `doc` (and its nested containers) must **not** be mutated; callers rely on
`doc` being unchanged after the call.

Each op is a dict with an `"op"` key. Supported ops:
- `{"op": "add", "path": p, "value": v}`
  - To an object: sets/overwrites the key at `p`.
  - To an array index: **inserts** `v` before the existing element at that index
    (indices shift right). Index equal to the length appends.
  - When the final token is `"-"` and the target is an array, append `v`.
- `{"op": "remove", "path": p}` — remove the value at `p`. A missing object key
  or out-of-range array index raises `PatchError`.
- `{"op": "replace", "path": p, "value": v}` — replace the value at `p`. A
  missing object key or out-of-range array index raises `PatchError`.
- Any other `"op"` value raises `PatchError`.

`path` strings are JSON Pointers parsed with `parse`; an invalid pointer
propagates `PointerError`.

## Acceptance scenarios (all deterministic)

1. `parse("/foo/bar") == ["foo", "bar"]`.
2. `parse("/a~1b/c~0d") == ["a/b", "c~d"]` (escaping; `~1`→`/`, `~0`→`~`).
3. `parse("") == []` (whole document).
4. `parse("foo")` raises `PointerError` (non-empty, no leading `/`).
5. `resolve({"a": {"b": 7}}, "/a/b") == 7` (nested object).
6. `resolve({"a": [10, 20, 30]}, "/a/2") == 30` (array index).
7. `resolve({"a": {"b": 7}}, "/a/x")` raises `ResolveError` (missing key).
8. `apply_patch({"a": 1}, [{"op": "add", "path": "/b", "value": 2}])
   == {"a": 1, "b": 2}` (add to object).
9. `apply_patch({"a": [1, 2]}, [{"op": "add", "path": "/a/-", "value": 3}])`
   yields `{"a": [1, 2, 3]}` (append with `"-"`); inserting at `/a/1` yields
   `{"a": [1, 9, 2]}`.
10. `apply_patch({"a": 1, "b": 2}, [{"op": "remove", "path": "/a"}]) == {"b": 2}`
    (remove); removing a missing key raises `PatchError`.
11. `apply_patch({"a": 1}, [{"op": "replace", "path": "/a", "value": 9}])
    == {"a": 9}` (replace); replacing a missing key raises `PatchError`.
12. Non-mutation: after `apply_patch(d, ops)`, the original `d` is unchanged.
13. Unknown op (e.g. `{"op": "frobnicate", ...}`) raises `PatchError`.
