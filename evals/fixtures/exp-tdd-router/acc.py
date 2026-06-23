from router import (
    compile_pattern,
    match_pattern,
    Router,
    NotFound,
    BuildError,
)

# --- pattern.py: match_pattern ---

# 1. static match -> empty dict
assert match_pattern(compile_pattern("/users/list"), "/users/list") == {}
# static does not match a different path
assert match_pattern(compile_pattern("/users/list"), "/users/other") is None

# 2. named param capture (str)
r = match_pattern(compile_pattern("/users/{id}"), "/users/alice")
assert r == {"id": "alice"}
assert isinstance(r["id"], str)
# named does not cross '/'
assert match_pattern(compile_pattern("/users/{id}"), "/users/a/b") is None

# 3. typed int yields int
r = match_pattern(compile_pattern("/users/{id:int}"), "/users/42")
assert r == {"id": 42}
assert isinstance(r["id"], int)

# 4. typed int rejects non-digit
assert match_pattern(compile_pattern("/users/{id:int}"), "/users/ab3") is None

# 5. wildcard captures the rest (including slashes)
r = match_pattern(compile_pattern("/files/{path:*}"), "/files/a/b/c.txt")
assert r == {"path": "a/b/c.txt"}
# wildcard requires at least one char
assert match_pattern(compile_pattern("/files/{path:*}"), "/files/") is None

# 6. no-match returns None (segment count mismatch)
assert match_pattern(compile_pattern("/users/{id}"), "/users/7/edit") is None
assert match_pattern(compile_pattern("/users/{id}"), "/users") is None

# --- core.py: Router ---

# 7. static beats param regardless of registration order
ro = Router()
ro.add("u", "/users/{id}", handler="H_param")
ro.add("me", "/users/me", handler="H_static")
name, params, handler = ro.match("/users/me")
assert name == "me"
assert params == {}
assert handler == "H_static"
# and a non-static path still hits the param route
name, params, handler = ro.match("/users/123")
assert name == "u"
assert params == {"id": "123"}

# 8. earliest-registered param wins
ro2 = Router()
ro2.add("a", "/x/{p}")
ro2.add("b", "/x/{q}")
name, params, handler = ro2.match("/x/7")
assert name == "a"
assert params == {"p": "7"}

# 9. NotFound raised on no match
ro3 = Router()
ro3.add("u", "/users/{id}")
raised = False
try:
    ro3.match("/nope/here")
except NotFound:
    raised = True
assert raised

# 10. reverse rebuilds the path
ro4 = Router()
ro4.add("user", "/users/{id:int}")
ro4.add("static", "/about/team")
assert ro4.reverse("user", id=5) == "/users/5"
assert ro4.reverse("static") == "/about/team"
# named param reverse (no special chars)
ro4.add("named", "/u/{handle}")
assert ro4.reverse("named", handle="alice") == "/u/alice"

# 11. reverse with missing param raises BuildError
raised = False
try:
    ro4.reverse("user")
except BuildError:
    raised = True
assert raised

# reverse with an extra (unknown) param raises BuildError
raised = False
try:
    ro4.reverse("user", id=5, bogus=1)
except BuildError:
    raised = True
assert raised

# reverse of an unknown route name raises BuildError
raised = False
try:
    ro4.reverse("does-not-exist")
except BuildError:
    raised = True
assert raised

print("OK")
