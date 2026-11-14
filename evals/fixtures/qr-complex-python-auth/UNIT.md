# Unit of work: slice 4 step 2 — API key verification

Complexity: complex

Stage 1 spec-compliance review: pass.

Changed files (see `diff.patch`):
- `app/auth/api_keys.py` — verifies API keys on every request (authentication)
- `tests/test_api_keys.py` — tests for it
- `docs/authentication.md` — documents the new header
