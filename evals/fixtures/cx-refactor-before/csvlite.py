"""CSV parser — typical test-first solution before REFACTOR review.

Written under strict RED-GREEN with one test per behavior. This is what
the test-first arm typically produces: correct, fully covered, but with
complexity that a REFACTOR review would catch and fix.
"""


def parse(text):
    if not text:
        return []
    rows = []
    current_row = []
    current_field = ""
    in_quotes = False
    i = 0
    while i < len(text):
        c = text[i]
        if in_quotes:
            if c == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    current_field += '"'
                    i += 2
                    continue
                else:
                    in_quotes = False
                    i += 1
                    continue
            else:
                current_field += c
                i += 1
                continue
        else:
            if c == '"':
                in_quotes = True
                i += 1
                continue
            elif c == ',':
                current_row.append(current_field)
                current_field = ""
                i += 1
                continue
            elif c == '\n':
                current_row.append(current_field)
                current_field = ""
                rows.append(current_row)
                current_row = []
                i += 1
                continue
            else:
                current_field += c
                i += 1
                continue
    if current_field or current_row:
        current_row.append(current_field)
        rows.append(current_row)
    return rows
