import ledger
from ledger import Ledger, LedgerError, UnbalancedError
from ledger import trial_balance, total_debits, total_credits
from ledger.report import balances_by_currency


def expect_raises(exc, fn):
    try:
        fn()
    except exc:
        return
    raise AssertionError("expected %s" % exc.__name__)


# --- Stage-2 change: multi-currency ---

lg = Ledger()
lg.open_account("cash_usd", "asset")                 # default currency USD
lg.open_account("sales_usd", "income", "USD")
lg.open_account("cash_eur", "asset", currency="EUR")
lg.open_account("sales_eur", "income", currency="EUR")

# per-currency balanced posting (USD nets 0, EUR nets 0)
lg.post(
    "2026-02-01",
    "mixed",
    [
        ("cash_usd", 1000),
        ("sales_usd", -1000),
        ("cash_eur", 2000),
        ("sales_eur", -2000),
    ],
)
assert lg.balance("cash_usd") == 1000
assert lg.balance("cash_eur") == 2000

# posting that balances overall but NOT per currency raises
expect_raises(
    UnbalancedError,
    lambda: lg.post(
        "2026-02-02",
        "cross",
        [("cash_usd", 1000), ("sales_eur", -1000)],
    ),
)

# balances_by_currency groups by currency
bbc = balances_by_currency(lg)
assert bbc == {
    "USD": {"cash_usd": 1000, "sales_usd": -1000},
    "EUR": {"cash_eur": 2000, "sales_eur": -2000},
}, bbc

# trial_balance with currency filter
assert trial_balance(lg, currency="EUR") == [
    ("cash_eur", 2000),
    ("sales_eur", -2000),
], trial_balance(lg, currency="EUR")

# default trial_balance sorted by (currency, name): EUR group before USD group
assert trial_balance(lg) == [
    ("cash_eur", 2000),
    ("sales_eur", -2000),
    ("cash_usd", 1000),
    ("sales_usd", -1000),
], trial_balance(lg)


# --- Regression: single-currency (USD) ledger behaves exactly as Stage 1 ---

reg = Ledger()
reg.open_account("cash", "asset")
reg.open_account("sales", "income")
reg.open_account("equity", "equity")            # opened but unused
reg.post("2026-01-01", "sale", [("cash", 1000), ("sales", -1000)])
reg.post("2026-01-04", "more cash", [("cash", 500), ("sales", -500)])

# regression 1: signed balances unchanged
assert reg.balance("cash") == 1500
assert reg.balance("sales") == -1500

# regression 2: default trial_balance still name-sorted, empty excluded
assert trial_balance(reg) == [("cash", 1500), ("sales", -1500)], trial_balance(reg)

# regression 3: totals unchanged
assert total_debits(reg) == total_credits(reg) == 1500

# regression 4: still-balanced single-currency post still raises when unbalanced
expect_raises(
    UnbalancedError,
    lambda: reg.post("2026-01-05", "bad", [("cash", 1000), ("sales", -900)]),
)

print("OK")
