# Surviving mutants from the last mutmut run on lib/names.py

mutmut is not installed in this environment; this report is the output of the
last run, and `mutants/check_mutants.py` re-checks the same mutants with pytest.

| Mutant | Line | Change |
|---|---|---|
| upper-removed | 9 | `word[0].upper()` -> `word[0]` |
| dot-removed | 9 | `+ "."` -> `+ ""` |
| empty-returns-dot | 8 | `return ""` -> `return "."` |
| first-letter-to-last | 9 | `word[0]` -> `word[-1]` |
