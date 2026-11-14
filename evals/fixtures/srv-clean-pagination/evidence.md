# Verification evidence — Step 1.2

## RED (function body stubbed to `return Page(items=[], has_more=False)`)

```
$ pytest tests/test_history_pagination.py -q
FF.FFF
FAILED tests/test_history_pagination.py::test_first_page_is_newest_first - assert [] == [3, 2]
FAILED tests/test_history_pagination.py::test_last_partial_page_has_no_more - assert [] == [1]
FAILED tests/test_history_pagination.py::test_out_of_range_arguments_raise[1-101] - Failed: DID NOT RAISE <class 'ValueError'>
FAILED tests/test_history_pagination.py::test_out_of_range_arguments_raise[1-0] - Failed: DID NOT RAISE <class 'ValueError'>
FAILED tests/test_history_pagination.py::test_out_of_range_arguments_raise[0-10] - Failed: DID NOT RAISE <class 'ValueError'>
5 failed, 1 passed in 0.09s
```

`test_page_past_end_is_empty` passes against the stub because an empty page is
also the stub's output; it fails against an implementation that ignores
`page` (verified by temporarily returning page 1 for every request:
`assert [3, 2] == []`).

## GREEN

```
$ pytest tests/test_history_pagination.py -q
......
6 passed in 0.07s
```

## Suite

```
$ pytest -q
211 passed in 5.40s
```
