# Feature: URL router (patterns + match + reverse)

Implement a small URL router across two modules. `import router` must work and
expose the public API below. All paths are absolute (start with `/`) and use `/`
as the segment separator.

## Module: `router/pattern.py`

### `compile_pattern(pattern: str) -> compiled`

Compile a pattern string into an opaque "compiled" object (any internal
representation). The pattern is a sequence of `/`-separated segments. Each
segment is one of:

- **static** — a literal string, e.g. `users` in `/users/list`.
- **named param** — `{name}`, matches exactly one non-empty segment (no `/`),
  captured as a string under key `name`.
- **typed int param** — `{name:int}`, matches one segment consisting only of
  ASCII digits `0-9`; the captured value is a Python `int`.
- **trailing wildcard** — `{name:*}`, only valid as the LAST segment; captures
  the entire remaining path (one or more segments, INCLUDING the `/`
  separators) as a string under key `name`. It matches at least one character.

Patterns with no params are purely static.

### `match_pattern(compiled, path: str) -> dict | None`

Match `path` against a compiled pattern.

- On a successful match, return a `dict` of captured params (empty `dict` `{}`
  if the pattern has no params). Int params yield `int` values; named and
  wildcard params yield `str` values.
- On no match, return `None`.

Matching rules:
- A static pattern matches only the identical path.
- `{name}` matches a single non-empty segment; it does NOT match across `/`.
- `{id:int}` matches `/users/42` (yielding `{"id": 42}`) but NOT `/users/abc`
  (returns `None`).
- `{path:*}` in `/files/{path:*}` matches `/files/a/b/c.txt`, yielding
  `{"path": "a/b/c.txt"}`. It does NOT match `/files` or `/files/` (the
  wildcard requires at least one character after the preceding `/`).
- Segment counts must line up: `/users/{id}` matches `/users/7` but not
  `/users` or `/users/7/edit`.

## Module: `router/core.py`

### `class Router`

`Router()` constructs an empty router.

#### `add(name: str, pattern: str, handler=None) -> None`
Register a route under the unique `name`, compiling `pattern`. `handler` is an
arbitrary object stored alongside the route (default `None`).

#### `match(path: str) -> (name, params, handler)`
Return a 3-tuple `(name, params, handler)` for the matching route, where
`params` is the dict from `match_pattern`.

**Precedence (exact rules):**
1. An **exact static** route whose pattern equals `path` literally always wins,
   regardless of registration order, over any param/wildcard route that also
   matches.
2. Otherwise, among the routes that match (param and/or wildcard routes), the
   **earliest-registered** one wins.

If no route matches, raise `NotFound` (exported from `router`).

#### `reverse(name: str, **params) -> str`
Rebuild the URL path for the named route by substituting `params` into its
pattern.

- Every param placeholder in the pattern must be supplied exactly once; a
  missing placeholder raises `BuildError`.
- Supplying a param name that is not a placeholder in the pattern (an extra
  param) raises `BuildError`.
- Int params accept an `int` (or its `str` form) and render as the decimal
  string. Named and wildcard params render as their `str` value.
- If `name` is not a registered route, raise `BuildError`.

`NotFound` and `BuildError` are both exported from the top-level `router`
package.

## Acceptance scenarios (deterministic)

1. **Static match** — `match_pattern(compile_pattern("/users/list"), "/users/list") == {}`.
2. **Named param capture** — `match_pattern(compile_pattern("/users/{id}"), "/users/alice") == {"id": "alice"}`.
3. **Typed int yields int** — `match_pattern(compile_pattern("/users/{id:int}"), "/users/42") == {"id": 42}` and the value is an `int`.
4. **Typed int rejects non-digit** — same pattern against `/users/ab3` returns `None`.
5. **Wildcard captures rest** — `match_pattern(compile_pattern("/files/{path:*}"), "/files/a/b/c.txt") == {"path": "a/b/c.txt"}`.
6. **No-match returns None** — `match_pattern(compile_pattern("/users/{id}"), "/users/7/edit") is None`.
7. **Router static beats param** — with `add("u","/users/{id}")` registered BEFORE `add("me","/users/me")`, `match("/users/me")` returns the `me` route (static wins despite later registration).
8. **Router earliest param wins** — with `add("a","/x/{p}")` then `add("b","/x/{q}")`, `match("/x/7")` returns the `a` route (earliest param).
9. **NotFound raised** — `match("/nope")` against a router with no matching route raises `NotFound`.
10. **reverse rebuilds path** — `reverse("user", id=5)` for route `/users/{id:int}` returns `"/users/5"`.
11. **reverse missing param raises** — `reverse("user")` (no `id`) for `/users/{id:int}` raises `BuildError`.
