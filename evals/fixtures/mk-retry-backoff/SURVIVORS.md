# Surviving mutants from the last mutmut run on lib/backoff.py

mutmut is not installed in this environment; this report is the output of the
last run. `mutants/check_mutants.py` re-checks every mutant below except the one
marked equivalent.

| Mutant | Line | Change | Note |
|---|---|---|---|
| exponent-off-by-one | 18 | `2 ** (attempt - 1)` -> `2 ** attempt` | |
| cap-removed | 19 | `return min(delay, MAX_DELAY_SECONDS)` -> `return delay` | |
| attempt-floor-lt-to-lte | 14 | `attempt < 1` -> `attempt <= 1` | |
| max-attempts-gt-to-gte | 16 | `attempt > MAX_ATTEMPTS` -> `attempt >= MAX_ATTEMPTS` | |
| exhausted-guard-removed | 17 | `raise RetriesExhausted(attempt)` -> `pass` | |
| delays-list-to-tuple | 24 | `delays = []` -> `delays = list()` | equivalent: same behaviour; no test can kill it |
