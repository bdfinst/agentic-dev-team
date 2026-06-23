import tmpl
from tmpl import render, TemplateError

# 1. plain text passthrough
assert render("hello world", {}) == "hello world"

# 2. variable substitution
assert render("Hi {{name}}!", {"name": "Sam"}) == "Hi Sam!"
assert render("{{ name }}", {"name": "Sam"}) == "Sam"  # tag whitespace trimmed
assert render("n={{n}}", {"n": 42}) == "n=42"          # str() coercion

# 3. missing variable -> "" (optional form so Stage-1 stays valid after the change)
assert render("[{{missing?}}]", {}) == "[]"

# 4. HTML escaping for {{x}}
assert render("{{x}}", {"x": "<a> & \"b\""}) == "&lt;a&gt; &amp; &quot;b&quot;"

# 5. unescaped triple {{{x}}}
assert render("{{{x}}}", {"x": "<a> & \"b\""}) == "<a> & \"b\""

# 6. list section iterates with element-as-context
assert render("{{#xs}}({{v}}){{/xs}}", {"xs": [{"v": 1}, {"v": 2}]}) == "(1)(2)"
assert render("{{#xs}}.{{/xs}}", {"xs": [1, 2, 3]}) == "..."

# 7. truthy non-list section renders once
assert render("{{#ok}}yes{{/ok}}", {"ok": True}) == "yes"
assert render("{{#u}}{{name}}{{/u}}", {"u": {"name": "Q"}}) == "Q"  # dict ctx

# 8. falsy / empty-list section renders nothing
assert render("{{#ok}}yes{{/ok}}", {"ok": []}) == ""
assert render("{{#ok}}yes{{/ok}}", {"ok": False}) == ""
assert render("{{#ok}}yes{{/ok}}", {}) == ""  # missing section key -> falsy

# 9. inverted section on falsy renders
assert render("{{^ok}}no{{/ok}}", {"ok": []}) == "no"
assert render("{{^ok}}no{{/ok}}", {"ok": True}) == ""

# 10. partial inclusion (rendered with current context)
assert render("{{>row}}", {"v": 7}, {"row": "<{{v}}>"}) == "<7>"

# 10b. missing partial -> ""
assert render("{{>missing}}", {}) == ""
assert render("{{>missing}}", {}, {}) == ""

# 11. unclosed / mismatched section raises TemplateError
for bad in ("{{#a}}x", "{{#a}}x{{/b}}", "{{/a}}"):
    try:
        render(bad, {})
        raised = False
    except TemplateError:
        raised = True
    assert raised, bad

print("OK")
