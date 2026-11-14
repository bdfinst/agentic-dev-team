# Plan excerpt: Document API — Slice 2, Step 2.1

### Slice 2: Fetch a document

**Files:** `docs_api/routes/documents.py`, `tests/test_documents_get.py`

```gherkin
Feature: Fetch a document

  Scenario: Active document is returned
    # Still passes if: the JSON keys are returned in a different order
    Given an active document "D-1" titled "Q3 report"
    When a client requests document "D-1"
    Then the response status is 200
    And the response body has title "Q3 report"

  Scenario: Unknown document
    # Still passes if: the 404 body adds a "detail" field
    Given no document "D-404" exists
    When a client requests document "D-404"
    Then the response status is 404
    And the response body has error "NOT_FOUND"

  Scenario: Archived document
    # Still passes if: the 410 body adds an "archived_at" field
    Given an archived document "D-2"
    When a client requests document "D-2"
    Then the response status is 410
    And the response body has error "ARCHIVED"
```

#### Step 2.1: `GET /documents/<id>`

**Complexity**: standard
**IMPLEMENT**: Route returning the document, 404 for unknown ids, 410 for archived documents
**TEST**: One test per scenario above
**REFACTOR**: Extract `_error(status, code)`
**Files**: `docs_api/routes/documents.py`, `tests/test_documents_get.py`
**Acceptance criteria for this step**:
- AC2.1: `GET /documents/<id>` for an active document returns 200 with `id`, `title`, `updated_at`.
- AC2.2: An unknown id returns 404 with body `{"error": "NOT_FOUND"}`.
- AC2.3: An archived document returns 410 with body `{"error": "ARCHIVED"}`.
