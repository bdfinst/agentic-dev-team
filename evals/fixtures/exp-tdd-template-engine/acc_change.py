from tmpl import render, TemplateError

# --- Change 1: missing variable now raises TemplateError ---
for bad in ("{{name}}", "{{{name}}}", "x {{a}} y"):
    try:
        render(bad, {})
        raised = False
    except TemplateError:
        raised = True
    assert raised, bad

# missing var inside a partial also raises
try:
    render("{{>row}}", {}, {"row": "{{v}}"})
    raised = False
except TemplateError:
    raised = True
assert raised

# --- Change 2: optional variables ({{name?}}) opt out of the error ---
assert render("[{{maybe?}}]", {}) == "[]"            # missing -> empty
assert render("[{{maybe?}}]", {"maybe": "x"}) == "[x]"  # present -> value
assert render("{{maybe?}}", {"maybe": "<b>"}) == "&lt;b&gt;"  # escaping still applies
assert render("{{{maybe?}}}", {}) == ""              # triple optional missing -> empty
assert render("{{{maybe?}}}", {"maybe": "<b>"}) == "<b>"  # triple optional present, unescaped

# --- Change 3: comments render nothing ---
assert render("a{{! note }}b", {}) == "ab"
assert render("{{!comment}}done", {}) == "done"
assert render("x{{! drop this }}y{{! and this }}z", {}) == "xyz"

# --- Regression: Stage-1 behavior preserved for present vars ---
# present variable substitution
assert render("Hi {{name}}!", {"name": "Sam"}) == "Hi Sam!"
# HTML escaping still applies to present vars
assert render("{{x}}", {"x": "<a> & \"b\""}) == "&lt;a&gt; &amp; &quot;b&quot;"
# triple still unescaped
assert render("{{{x}}}", {"x": "<a>"}) == "<a>"
# list section still iterates
assert render("{{#xs}}({{v}}){{/xs}}", {"xs": [{"v": 1}, {"v": 2}]}) == "(1)(2)"
# truthy / falsy / inverted sections unchanged; missing section key still falsy (no raise)
assert render("{{#ok}}yes{{/ok}}", {"ok": True}) == "yes"
assert render("{{#ok}}yes{{/ok}}", {}) == ""
assert render("{{^ok}}no{{/ok}}", {"ok": []}) == "no"
# partials with present context unchanged
assert render("{{>row}}", {"v": 7}, {"row": "<{{v}}>"}) == "<7>"
# missing partial still ""
assert render("{{>missing}}", {}) == ""
# unclosed section still raises
try:
    render("{{#a}}x", {})
    raised = False
except TemplateError:
    raised = True
assert raised

print("OK")
