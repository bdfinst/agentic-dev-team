# Plan: Better product search

**Created**: 2026-11-10
**Branch**: feat/search-engine
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Improve the search experience so it feels modern and works better for users.
We will build our own search engine module inside the catalog service so we
control relevance end to end.

Context: the catalog is 4,000 products in the existing Postgres database.
Search today is `WHERE name ILIKE '%' || :q || '%'`.

## Acceptance Criteria

- [ ] AC1: Search returns products whose name or description contains the query terms.
- [ ] AC2: Misspellings within edit distance 2 still match ("mugg" finds "mug").
- [ ] AC3: Results are ranked by relevance (BM25 over name and description).
- [ ] AC4: The index updates within 5 seconds of a product change.

## Slices

### Slice 1: In-house search engine

**Depends-on:** none
**Files:** `catalog/search/tokenizer.py`, `catalog/search/inverted_index.py`, `catalog/search/bm25.py`, `catalog/search/levenshtein.py`, `catalog/search/index_worker.py`, `catalog/search/api.py`, `tests/search/`

**Behavior:**

```gherkin
Feature: Product search

  Scenario: Misspelled query still matches
    # Still passes if: results are sorted alphabetically
    Given a product named "Blue enamel mug"
    When a shopper searches for "mugg"
    Then "Blue enamel mug" is in the results

  Scenario: Relevance ranking
    # Still passes if: description matches are weighted the same as name matches
    Given products "Mug" and "Mug rack with mug hooks"
    When a shopper searches for "mug"
    Then both products are in the results
```

**Steps:**

#### Step 1.1: Tokenizer with stemming and stop words

**Complexity**: complex
**Files**: `catalog/search/tokenizer.py`, `tests/search/test_tokenizer.py`
**Covers**: AC1

#### Step 1.2: In-memory inverted index with on-disk snapshots

**Complexity**: complex
**Files**: `catalog/search/inverted_index.py`, `tests/search/test_inverted_index.py`
**Covers**: AC1

#### Step 1.3: BM25 scorer

**Complexity**: complex
**Files**: `catalog/search/bm25.py`, `tests/search/test_bm25.py`
**Covers**: AC3

#### Step 1.4: Levenshtein automaton for fuzzy matching

**Complexity**: complex
**Files**: `catalog/search/levenshtein.py`, `tests/search/test_levenshtein.py`
**Covers**: AC2

#### Step 1.5: Background worker that tails product changes into the index

**Complexity**: complex
**Files**: `catalog/search/index_worker.py`, `tests/search/test_index_worker.py`
**Covers**: AC4

#### Step 1.6: Replace the ILIKE query with the new engine

**Complexity**: standard
**Files**: `catalog/search/api.py`, `tests/search/test_api.py`
**Covers**: AC1, AC2, AC3

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Risks & Open Questions

- Snapshot format may need to change as the engine evolves.
