"""Keep pytest from collecting fixture data as if it were real test code.

`fixtures/recorded-diffs/**/files/tests/test_widget.py` (#2051) is a
synthetic *recorded-diff* case — content the recorded-diff adapter reviews,
not a test of this repo's own code. It intentionally matches pytest's
default `test_*.py` collection glob (it has to, to prove the adapter's
`diff_shape` classifier sees real test-shaped content), so a broad
`pytest evals/code-review-benchmark ...` invocation would otherwise import
and collect it — generating a `__pycache__` bytecode-cache file inside the
fixture's `files/` tree. That stray `.pyc` file then pollutes
`recorded_diff_adapter._relative_files()`'s output: the fixture stops being
provably test-only (`is_test_only()` correctly refuses to classify a `.pyc`
as a test file), and `test_list_cases_finds_the_real_fixture_and_classifies
_test_only` in `tests/scripts/test_code_review_benchmark_recorded_diff_
adapter.py` flips from green to red depending on which pytest invocation
ran first — a real, reproduced bug, not a hypothetical one.
"""

collect_ignore_glob = ["recorded-diffs/**"]
