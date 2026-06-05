# Stack profile — Django / Python

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical Django/Python tool.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | pytest (or `unittest`); `unittest.mock` for collaborators | call functions/methods directly; no DB |
| Component / Service | `pytest-django` + DRF `APIClient` / Django `Client` | drive the view/endpoint in-process; double outbound deps |
| Integration | `pytest-django` with the real test DB (transactional fixtures) | models, migrations, ORM queries, serializers against a real DB |
| Contract | Pact (Python) or `schemathesis` against the OpenAPI spec | provider/consumer agreement (`microservice-testing.md`) |
| E2E | Playwright (Python) / Selenium | critical journeys only |

**Notes.** `freezegun` (or inject a clock) for time; `responses`/`httpx` mock for outbound HTTP — double the **owned adapter**, not the third-party SDK. Use `pytest.mark.django_db` deliberately; a test that doesn't need the DB shouldn't take it (speed). For Flask/FastAPI substitute the app's test client (`app.test_client()` / `TestClient`) at the component layer — the layer mapping is identical.
