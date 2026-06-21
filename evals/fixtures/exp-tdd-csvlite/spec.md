# Feature: CSV parsing (csvlite.py)
Implement `parse(text)` in `csvlite.py`. Rows separated by newlines, fields by
commas. A field may be double-quoted to contain commas; inside a quoted field a
literal double quote is written as two double quotes (""). Return a list of rows,
each a list of string fields. `parse("")` returns `[]`.
