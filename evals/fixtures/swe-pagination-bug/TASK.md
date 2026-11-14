# Bug: the last page drops items

Reported by support: with 25 items and a page size of 10, page 3 is empty, but it
should hold items 21-25. Page 1 also seems to start at the second item.

Fix `listing/pages.py`. Expected behaviour:

1. Pages are 1-based: `page(items, 1, 10)` returns items 1-10.
2. The last page returns whatever remains (5 items for 25 items, size 10).
3. `page_count(25, 10)` is 3; `page_count(0, 10)` is 0.
4. A page number below 1, or a page size below 1, raises `ValueError`.
5. A page past the end returns an empty list.

`tests/test_acceptance.py` reproduces the report and must pass unchanged;
the existing tests must keep passing. Run:

    python3 -m unittest discover -s tests -t .
