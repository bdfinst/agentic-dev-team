# Surviving mutants from the last mutmut run on shop/shipping.py

mutmut is not installed in this environment; this report is the output of the
last run, and `mutants/check_mutants.py` re-checks the same mutants with pytest.

| Mutant | Line | Change |
|---|---|---|
| threshold-gte-to-gt | 11 | `subtotal >= FREE_SHIPPING_THRESHOLD` -> `subtotal > FREE_SHIPPING_THRESHOLD` |
| heavy-gt-to-gte | 12 | `weight_kg > HEAVY_KG` -> `weight_kg >= HEAVY_KG` |
| surcharge-removed | 13 | `fee += HEAVY_SURCHARGE` -> `fee += 0` |
