# Behavior to design tests for

Bug fix. An off-by-one error in the CSV row parser drops the last row of every
file. The defect was **discovered while running the parser's unit tests** — a
unit test exercising a 3-row file returned only 2 rows.

Add a regression test that pins the corrected behavior. The bug was found at the
unit level, in pure parsing logic with no UI and no I/O.
