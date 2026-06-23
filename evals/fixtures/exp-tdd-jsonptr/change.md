# Change: move/copy ops, lenient object remove, and resolve_default

This change MODIFIES existing behavior across two modules.

## `jsonptr/patch.py`

1. Add two new ops to `apply_patch`:
   - `{"op": "move", "from": f, "path": p}` — remove the value at the `"from"`
     pointer, then `add` it at `"path"` (array-insert / `"-"` append semantics
     apply at the destination, same as `add`).
   - `{"op": "copy", "from": f, "path": p}` — resolve the value at `"from"`
     (leaving it in place) and `add` a copy of it at `"path"`.

2. **Change `remove` semantics for objects:** removing a non-existent OBJECT key
   is now a **no-op** (the document is returned unchanged for that op) instead of
   raising `PatchError`. Removing an out-of-range / non-decimal ARRAY index still
   raises `PatchError`. `replace` is unchanged — a missing key still raises.

## `jsonptr/pointer.py`

3. Add `resolve_default(doc, pointer, default)` — like `resolve`, but returns
   `default` instead of raising `ResolveError` on any miss (missing key,
   out-of-range index, non-container, non-decimal token). A `PointerError` for a
   syntactically invalid pointer still propagates. Export it from
   `jsonptr/__init__.py`.

The non-mutation guarantee of `apply_patch` still holds for all ops, including
`move` and `copy`.
