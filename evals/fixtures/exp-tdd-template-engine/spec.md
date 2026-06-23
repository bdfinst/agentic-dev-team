# Feature: a tiny Mustache-like template engine (`tmpl`)

Implement a small template engine split across two modules in the `tmpl`
package. `import tmpl` must work and expose `render` and `TemplateError`.

## Public API (exact signatures)

In `tmpl/render.py` (re-exported from `tmpl/__init__.py`):

```python
render(template: str, context: dict, partials: dict | None = None) -> str
```

In `tmpl/parser.py` (re-exported from `tmpl/__init__.py`):

```python
parse(template: str) -> list   # template -> list of nodes
class TemplateError(Exception): ...
```

`parser.py` turns the template string into a list of nodes (text, variable,
triple-variable, section, inverted-section, partial). `render.py` walks those
nodes with a context dict and a partials dict. The node representation is
internal; tests use `render` (and that `parse` raises on bad input).

## Semantics

1. **Plain text passthrough.** Text outside `{{...}}` is emitted verbatim.
2. **Variable substitution.** `{{name}}` renders `str(context["name"])`.
3. **Missing variable.** A `{{name}}` whose key is absent from the context
   renders the empty string `""`.
4. **HTML escaping (default).** `{{x}}` HTML-escapes its value. The characters
   `&`, `<`, `>`, and `"` become `&amp;`, `&lt;`, `&gt;`, and `&quot;`
   respectively. `&` is replaced first.
5. **Unescaped triple.** `{{{x}}}` renders the value WITHOUT escaping.
6. **List section.** `{{#items}}...{{/items}}` where `items` is a list renders
   the inner block once per element. When an element is a dict, that dict
   becomes the context for the inner block. (A non-dict element is rendered with
   the same outer context.)
7. **Truthy non-list section.** If the section value is truthy and not a list
   (e.g. `True`, a non-empty string, a dict), the inner block renders exactly
   once. When the value is a dict, that dict is the inner context.
8. **Falsy section.** If the section value is falsy or an empty list (`False`,
   `0`, `""`, `None`, `[]`, or a missing key), the inner block renders nothing.
9. **Inverted section.** `{{^items}}...{{/items}}` renders the inner block ONLY
   when the value is falsy or an empty list (the complement of a section), and
   renders nothing when the value is truthy/non-empty.
10. **Partials.** `{{>name}}` renders `partials[name]` (a template string) with
    the current context. A missing partial (no such key, or `partials is None`)
    renders `""`.
11. **Unclosed / mismatched section.** A section that is never closed, or whose
    closing tag name does not match the open tag (e.g. `{{#a}}...{{/b}}`), or a
    stray closing tag with no matching open, raises `TemplateError` (raised from
    `parse`, and therefore from `render`).

Whitespace inside a tag is trimmed: `{{ name }}` is the variable `name`.

## Deterministic scenarios

- `render("hello world", {})` -> `"hello world"`
- `render("Hi {{name}}!", {"name": "Sam"})` -> `"Hi Sam!"`
- `render("[{{missing}}]", {})` -> `"[]"`
- `render("{{x}}", {"x": "<a> & \"b\""})` -> `"&lt;a&gt; &amp; &quot;b&quot;"`
- `render("{{{x}}}", {"x": "<a> & \"b\""})` -> `"<a> & \"b\""`
- `render("{{#xs}}({{v}}){{/xs}}", {"xs": [{"v": 1}, {"v": 2}]})` -> `"(1)(2)"`
- `render("{{#ok}}yes{{/ok}}", {"ok": True})` -> `"yes"`
- `render("{{#ok}}yes{{/ok}}", {"ok": []})` -> `""`
- `render("{{^ok}}no{{/ok}}", {"ok": []})` -> `"no"`
- `render("{{>row}}", {"v": 7}, {"row": "<{{v}}>"})` -> `"<7>"`
- `render("{{>missing}}", {})` -> `""`
- `parse("{{#a}}x")` raises `TemplateError`; `parse("{{#a}}x{{/b}}")` raises `TemplateError`.
