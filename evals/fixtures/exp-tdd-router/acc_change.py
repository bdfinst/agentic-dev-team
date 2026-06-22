from router import (
    compile_pattern,
    match_pattern,
    Router,
    NotFound,
    BuildError,
)

# === CHANGE 1: trailing-slash tolerance ===

# strict_slash=False makes a trailing slash optional
lenient = Router(strict_slash=False)
lenient.add("users", "/users", handler="H")
name, params, handler = lenient.match("/users/")
assert name == "users"
assert params == {}
assert handler == "H"
# and the un-slashed form still matches
assert lenient.match("/users")[0] == "users"

# default (strict) does NOT tolerate the trailing slash
strict = Router()  # default strict_slash=True
strict.add("users", "/users")
raised = False
try:
    strict.match("/users/")
except NotFound:
    raised = True
assert raised

# precedence still holds under lenient matching: static beats param
lenient2 = Router(strict_slash=False)
lenient2.add("p", "/users/{id}")
lenient2.add("me", "/users/me")
assert lenient2.match("/users/me/")[0] == "me"

# === CHANGE 2: slug type ===

assert match_pattern(compile_pattern("/p/{s:slug}"), "/p/hello-world") == {"s": "hello-world"}
assert match_pattern(compile_pattern("/p/{s:slug}"), "/p/Hello") is None      # uppercase
assert match_pattern(compile_pattern("/p/{s:slug}"), "/p/a_b") is None        # underscore
assert match_pattern(compile_pattern("/p/{s:slug}"), "/p/") is None           # empty

# slug routes work through the Router too
rs = Router()
rs.add("post", "/post/{slug:slug}")
name, params, handler = rs.match("/post/my-first-post")
assert name == "post"
assert params == {"slug": "my-first-post"}

# === CHANGE 3: reverse URL-encodes (except wildcard) ===

enc = Router()
enc.add("search", "/search/{q}")
enc.add("files", "/files/{path:*}")
enc.add("user", "/users/{id:int}")

assert enc.reverse("search", q="a b") == "/search/a%20b"     # space -> %20
assert enc.reverse("search", q="a/b") == "/search/a%2Fb"     # / -> %2F
assert enc.reverse("files", path="a/b/c") == "/files/a/b/c"  # wildcard unescaped
# plain values unaffected
assert enc.reverse("user", id=5) == "/users/5"

# === REGRESSION: Stage-1 behavior with default Router() unchanged ===

# regression 1: default matching + precedence (static beats param, earliest param)
reg = Router()
reg.add("u", "/users/{id}", handler="param")
reg.add("me", "/users/me", handler="static")
assert reg.match("/users/me") == ("me", {}, "static")
assert reg.match("/users/42") == ("u", {"id": "42"}, "param")

reg2 = Router()
reg2.add("a", "/x/{p}")
reg2.add("b", "/x/{q}")
assert reg2.match("/x/7")[0] == "a"

# regression 2: pattern types + NotFound + reverse with plain values
assert match_pattern(compile_pattern("/users/{id:int}"), "/users/42") == {"id": 42}
assert match_pattern(compile_pattern("/users/{id:int}"), "/users/x") is None
assert match_pattern(compile_pattern("/files/{path:*}"), "/files/a/b") == {"path": "a/b"}

raised = False
try:
    reg.match("/nope")
except NotFound:
    raised = True
assert raised

# reverse of a plain (no special-char) value is still the literal path
reg.add("named", "/u/{handle}")
assert reg.reverse("named", handle="alice") == "/u/alice"
raised = False
try:
    reg.reverse("named")
except BuildError:
    raised = True
assert raised

print("OK")
