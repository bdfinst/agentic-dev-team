"""CSV parser — post-REFACTOR review.

Same behavior as cx-refactor-before/csvlite.py, refactored by the REFACTOR
review loop (complexity-review + refactor-opportunity-review) after GREEN:
- parse() delegates character-class decisions to two focused helpers
- Nesting depth reduced from 4 → 2 in the main loop
- All tests still pass (tests unchanged, only production code refactored)
"""


def _consume_quoted_field(text, start):
    i = start + 1
    field = ""
    while i < len(text):
        c = text[i]
        if c == '"':
            if i + 1 < len(text) and text[i + 1] == '"':
                field += '"'
                i += 2
            else:
                return field, i + 1
        else:
            field += c
            i += 1
    return field, i


def _split_rows(text):
    rows = []
    current_row = []
    current_field = ""
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            current_field, i = _consume_quoted_field(text, i)
        elif c == ',':
            current_row.append(current_field)
            current_field = ""
            i += 1
        elif c == '\n':
            current_row.append(current_field)
            rows.append(current_row)
            current_row = []
            current_field = ""
            i += 1
        else:
            current_field += c
            i += 1
    if current_field or current_row:
        current_row.append(current_field)
        rows.append(current_row)
    return rows


def parse(text):
    if not text:
        return []
    return _split_rows(text)
