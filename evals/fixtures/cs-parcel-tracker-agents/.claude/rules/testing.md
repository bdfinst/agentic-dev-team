# Testing

- Put each suite in `tests/` and name it `<module>.test.ts`.
- Test routes through HTTP with `supertest`; do not call handlers directly.
- Stub carrier adapters at the module boundary; never call a real carrier API.
