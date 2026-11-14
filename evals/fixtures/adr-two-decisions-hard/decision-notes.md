# Platform sync, 2025-10-14: decisions

1. Logging helper cleanup. In `app/logging_setup.py` we now build the JSON
   formatter with a dict literal instead of `dict(...)` calls, and we sorted
   the keys alphabetically. Output fields are unchanged (`ts`, `level`, `msg`,
   `trace_id`). Ana did this in one PR; easy to undo.

2. Retire API v1. `/v1/orders` and `/v1/customers` stop responding on
   2026-03-31 and return 410 Gone after that. All 14 partners were notified
   on 2025-10-01; 11 already call `/v2`. The 3 remaining partners get a
   migration guide and a named contact. Why now: v1 carries a separate
   pricing code path that has caused two billing incidents this year, and
   keeping it means every pricing change is made twice. Once partners lose
   v1 access and we delete the v1 pricing path, bringing it back would mean
   rebuilding and re-certifying it. Alternative considered: freeze v1 and
   keep it running indefinitely; rejected because the duplicate pricing path
   is the incident source.
