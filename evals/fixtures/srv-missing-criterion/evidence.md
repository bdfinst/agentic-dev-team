# Verification evidence — Step 2.1

## RED (route not yet added)

```
$ pytest tests/test_documents_get.py -q
FF
FAILED tests/test_documents_get.py::test_active_document_is_returned - assert 404 == 200
FAILED tests/test_documents_get.py::test_unknown_document_returns_404 - AssertionError: assert None == {'error': 'NOT_FOUND'}
2 failed in 0.21s
```

## GREEN

```
$ pytest tests/test_documents_get.py -q
..
2 passed in 0.18s
```

## Suite

```
$ pytest -q
148 passed in 4.02s
```
