# Behavior to design tests for

The **funds-transfer amount calculation** — debiting one account and crediting
another, including fee and overdraft handling. This is **business-critical**:
an error moves real money incorrectly.

It is currently covered by **only a single unit test** of the calculation. The
persistence and transaction boundary around it have no coverage.
