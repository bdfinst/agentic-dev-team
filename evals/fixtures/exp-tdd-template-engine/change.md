# Change: strict missing variables, optional vars, and comments

Modify the engine's behavior. Two files change: `tmpl/parser.py` and
`tmpl/render.py`.

## 1. Missing variables are now an error (behavior change)

Previously a `{{name}}` (or `{{{name}}}`) whose key was absent rendered `""`.
Now a missing variable raises `TemplateError`.

- `render("{{name}}", {})` raises `TemplateError`.
- `render("{{{name}}}", {})` raises `TemplateError`.

## 2. Optional variables opt out of the error

A variable whose name ends with `?` is *optional*: when its key (the name
WITHOUT the trailing `?`) is missing, it renders `""` instead of raising. When
present, it renders normally.

- `render("[{{maybe?}}]", {})` -> `"[]"` (missing -> empty, no error).
- `render("[{{maybe?}}]", {"maybe": "x"})` -> `"[x]"` (present -> value).

The `?` applies to both escaped `{{maybe?}}` and triple `{{{maybe?}}}` forms,
and escaping still applies to the escaped optional form.

## 3. Comment syntax

`{{!comment}}` is a comment: it is parsed out and renders nothing. Its contents
(the text up to the closing `}}`) are ignored.

- `render("a{{! note }}b", {})` -> `"ab"`.
- `render("{{!comment}}done", {})` -> `"done"`.

## Unchanged

Present variables, HTML escaping, triple-unescaped, sections (list / truthy /
falsy), inverted sections, and partials all behave exactly as in `spec.md`.
Note that a missing **section** key still renders nothing (it is falsy) — only
missing plain `{{var}}` references raise. Inside a partial, a missing variable
also raises (the partial is rendered with the same rules).
