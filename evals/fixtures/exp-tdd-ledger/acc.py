import ledger
from ledger import Ledger, LedgerError, UnbalancedError
from ledger import trial_balance, total_debits, total_credits, account_statement


def expect_raises(exc, fn):
    try:
        fn()
    except exc:
        return
    raise AssertionError("expected %s" % exc.__name__)


# 1. open account -> zero balance
lg = Ledger()
lg.open_account("cash", "asset")
assert lg.balance("cash") == 0

# 2. duplicate open raises
expect_raises(LedgerError, lambda: lg.open_account("cash", "asset"))

# 3. invalid type raises
expect_raises(LedgerError, lambda: lg.open_account("bad", "bogus"))

# 4. balanced post updates balances
lg.open_account("sales", "income")
lg.post("2026-01-01", "sale", [("cash", 1000), ("sales", -1000)])
assert lg.balance("cash") == 1000
assert lg.balance("sales") == -1000

# 5. unbalanced post raises, balances unchanged
expect_raises(
    UnbalancedError,
    lambda: lg.post("2026-01-02", "bad", [("cash", 1000), ("sales", -900)]),
)
assert lg.balance("cash") == 1000
assert lg.balance("sales") == -1000

# 6. post to unknown account raises
expect_raises(
    LedgerError,
    lambda: lg.post("2026-01-03", "x", [("cash", 100), ("nope", -100)]),
)

# 7. signed balance accumulates
lg.open_account("equity", "equity")
lg.post("2026-01-04", "more cash", [("cash", 500), ("sales", -500)])
assert lg.balance("cash") == 1500

# 8. trial_balance sorted + excludes empty (equity opened but unused)
tb = trial_balance(lg)
assert tb == [("cash", 1500), ("sales", -1500)], tb

# 9. totals balance, positive
assert total_debits(lg) == total_credits(lg)
assert total_debits(lg) == 1500
assert total_credits(lg) == 1500

# 10. statement ordering
stmt = account_statement(lg, "cash")
assert stmt == [
    ("2026-01-01", "sale", 1000),
    ("2026-01-04", "more cash", 500),
], stmt

# unknown account on balance / statement raises
expect_raises(LedgerError, lambda: lg.balance("ghost"))
expect_raises(LedgerError, lambda: account_statement(lg, "ghost"))

print("OK")
