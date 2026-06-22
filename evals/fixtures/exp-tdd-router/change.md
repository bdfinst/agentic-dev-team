# Change: trailing-slash tolerance, slug type, and reverse URL-encoding

Modify the router. Three behavior changes, touching both `router/pattern.py` and
`router/core.py`. The default behavior of `Router()` must remain exactly as in
Stage 1 (`strict_slash=True`).

## 1. Optional trailing-slash tolerance (`router/core.py`)

`Router(strict_slash=True)` is the default and preserves Stage-1 matching
exactly. `Router(strict_slash=False)` makes a single trailing slash optional
when matching:

- A path of `"/users/"` matches a route registered as `"/users"` (and vice
  versa), by normalizing a trailing `/` off the incoming path before matching
  (the root path `"/"` is left as-is).
- Trailing-slash normalization applies to the whole path before route matching;
  precedence rules (static beats param, earliest param wins) are unchanged.
- With `strict_slash=True` (default), `"/users/"` does NOT match `"/users"`.

## 2. New typed param `{name:slug}` (`router/pattern.py`)

Add a `slug` type: `{name:slug}` matches a single segment consisting only of
characters in `[a-z0-9-]` (lowercase letters, digits, hyphen), one or more
characters. The captured value is a `str`.

- `match_pattern(compile_pattern("/p/{s:slug}"), "/p/hello-world") == {"s": "hello-world"}`.
- `/p/Hello` (uppercase) and `/p/a_b` (underscore) return `None`.

## 3. `reverse` URL-encodes param values (`router/pattern.py` helper + `router/core.py`)

`reverse` now percent-encodes substituted param values:

- A space ` ` becomes `%20` and a `/` becomes `%2F` in named, int, and slug
  params.
- **Exception:** wildcard (`{name:*}`) params are NOT encoded — their `/`
  separators are preserved literally.

Examples (route `/search/{q}` with a wildcard route `/files/{path:*}`):
- `reverse("search", q="a b")` returns `"/search/a%20b"`.
- `reverse("search", q="a/b")` returns `"/search/a%2Fb"`.
- `reverse("files", path="a/b/c")` returns `"/files/a/b/c"` (wildcard unescaped).

Place the encoding logic in a small helper in `router/pattern.py` and call it
from `Router.reverse` in `router/core.py`.

## Compatibility

All Stage-1 behavior with the default `Router()` (and `compile_pattern` /
`match_pattern` for the existing types) must continue to pass unchanged.
