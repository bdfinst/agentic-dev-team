# Feature: a double-entry ledger (accounts + postings + reports)

Implement a small double-entry bookkeeping ledger across the `ledger` package.
**All monetary amounts are integer cents — never use floats.** In a posting's
entries a **positive** amount is a **debit** and a **negative** amount is a
**credit**; every posting must balance (its entry amounts sum to zero).

`import ledger` must work and expose every name listed below.

## Module `ledger/accounts.py`

Exceptions (also re-exported from `ledger`):

- `LedgerError` — invalid ledger operation (duplicate account, unknown account,
  invalid account type).
- `UnbalancedError` — a posting whose entry amounts do not sum to zero.

Class `Ledger`:

- `open_account(name, type)` — open an account `name` whose `type` is one of
  `"asset"`, `"liability"`, `"equity"`, `"income"`, `"expense"`. Opening a
  duplicate `name` raises `LedgerError`. An invalid `type` raises `LedgerError`.
- `post(date, description, entries)` — record a posting. `entries` is a list of
  `(account_name, amount_cents)` tuples (positive = debit, negative = credit).
  - If the amounts do not sum to `0`, raise `UnbalancedError`.
  - If any `account_name` is not an open account, raise `LedgerError`.
  - On success the posting is appended in call order.
- `balance(account_name)` — return the signed integer-cents balance of the
  account: the sum of all entry amounts posted to it. Returns `0` for an open
  account with no postings. Unknown account raises `LedgerError`.

## Module `ledger/report.py`

- `trial_balance(ledger)` — return a list of `(name, balance_cents)` tuples for
  every account that has **at least one posting**, **sorted by account name**.
  Accounts with no postings are excluded.
- `total_debits(ledger)` — return the sum of all **positive** entry amounts
  across all postings, as a positive integer-cents value.
- `total_credits(ledger)` — return the sum of `-amount` over all **negative**
  entry amounts across all postings, as a positive integer-cents value. For a
  valid ledger `total_debits(ledger) == total_credits(ledger)`.
- `account_statement(ledger, name)` — return a list of
  `(date, description, amount_cents)` for every posting that touches `name`, in
  posting order. Unknown account raises `LedgerError`.

## Acceptance scenarios (deterministic)

1. **Open account.** `open_account("cash", "asset")` then `balance("cash") == 0`.
2. **Duplicate open raises.** Opening `"cash"` a second time raises `LedgerError`.
3. **Invalid type raises.** `open_account("x", "bogus")` raises `LedgerError`.
4. **Balanced post updates balances.** After
   `post("2026-01-01", "sale", [("cash", 1000), ("sales", -1000)])`,
   `balance("cash") == 1000` and `balance("sales") == -1000`.
5. **Unbalanced post raises.** `post("d", "x", [("cash", 1000), ("sales", -900)])`
   raises `UnbalancedError` and leaves balances unchanged.
6. **Post to unknown account raises.** Posting that names an unopened account
   raises `LedgerError`.
7. **Signed balance accumulates.** Two postings debiting `cash` 1000 and 500
   give `balance("cash") == 1500`.
8. **trial_balance sorted + excludes empty.** With accounts `cash`, `sales`, and
   an opened-but-unused `equity`, `trial_balance` returns only `cash` and
   `sales`, sorted by name: `[("cash", ...), ("sales", ...)]` — `equity` absent.
9. **Totals balance.** Across all valid postings,
   `total_debits(lg) == total_credits(lg)`, both positive cents.
10. **Statement ordering.** `account_statement(lg, "cash")` returns the postings
    touching `cash` in the order they were posted, each as
    `(date, description, amount_cents)`.
