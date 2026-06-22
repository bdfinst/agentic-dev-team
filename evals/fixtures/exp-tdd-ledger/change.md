# Change: multi-currency support

Extend the ledger so accounts carry a currency and postings balance **per
currency**. Amounts remain integer cents throughout.

## `ledger/accounts.py`

- `open_account(name, type, currency="USD")` — accounts now have a currency.
  Existing single-argument-currency callers (no `currency=`) get `"USD"`.
- `post(date, description, entries)` — `entries` are still
  `(account_name, amount_cents)` tuples, but a posting must now balance **per
  currency**: group each entry by the currency of its account and require **each
  currency's amounts to sum to zero**. If any currency group is non-zero, raise
  `UnbalancedError`. (A single-currency posting therefore behaves exactly as
  before.) Unknown-account and append-order behavior are unchanged.
- `balance(name)` is unchanged (signed cents for that account).

## `ledger/report.py`

- Add `balances_by_currency(ledger)` — return a dict mapping each currency to a
  dict of `{account_name: balance_cents}`, including only accounts that have at
  least one posting. Shape: `{ "USD": {"cash": 1000, ...}, "EUR": {...} }`.
- `trial_balance(ledger, currency=None)` — gains an optional `currency` filter.
  - `currency=None` (default): include all posted accounts, sorted by
    `(currency, name)`.
  - `currency="EUR"`: include only posted accounts in that currency, sorted by
    name.

  For an all-`USD` ledger the default ordering is unchanged from Stage 1 (sorted
  by name), because every currency key is identical.

`total_debits` and `total_credits` are unchanged (they sum raw amounts across
all postings regardless of currency).
