from sheet import Sheet, CycleError

# --- Change 1: MAX and MIN over ranges ---
s = Sheet()
s.set_cell("A1", 3)
s.set_cell("A2", 9)
s.set_cell("A3", 5)
s.set_cell("B1", "=MAX(A1:A3)")
s.set_cell("B2", "=MIN(A1:A3)")
assert s.get_value("B1") == 9.0
assert s.get_value("B2") == 3.0

# MAX/MIN treat empty cells as 0.0
s = Sheet()
s.set_cell("A1", 4)
s.set_cell("A2", 7)
# B1, B2 empty within the rectangle
s.set_cell("C1", "=MIN(A1:B2)")
s.set_cell("C2", "=MAX(A1:B2)")
assert s.get_value("C1") == 0.0  # empty cells count as 0
assert s.get_value("C2") == 7.0

# --- Change 2: SUM ignores "" cells but counts explicit 0 ---
s = Sheet()
s.set_cell("A1", 10)
s.set_cell("A2", "")
s.set_cell("A3", 0)
s.set_cell("B1", "=SUM(A1:A3)")
assert s.get_value("B1") == 10.0  # A2 skipped, A3 counts as 0
# raw of an "" cell is the empty string; get_value still 0.0
assert s.get_raw("A2") == ""
assert s.get_value("A2") == 0.0
# AVG is unchanged: "" and empty cells still count as 0.0 in sum and count
s.set_cell("B2", "=AVG(A1:A3)")
assert s.get_value("B2") == 10.0 / 3.0  # (10 + 0 + 0)/3

# --- Change 3: clear_cell ---
s = Sheet()
s.set_cell("A1", 42)
assert s.get_value("A1") == 42.0
s.clear_cell("A1")
assert s.get_raw("A1") is None
assert s.get_value("A1") == 0.0
# clearing a never-set cell is a no-op
s.clear_cell("Z9")
assert s.get_raw("Z9") is None

# --- Regression: Stage-1 behavior unchanged ---

# Regression 1: SUM over plain numbers still works
s = Sheet()
s.set_cell("A1", 1)
s.set_cell("A2", 2)
s.set_cell("A3", 3)
s.set_cell("B1", "=SUM(A1:A3)")
assert s.get_value("B1") == 6.0

# Regression 2: AVG over a rectangle unchanged
s = Sheet()
s.set_cell("A1", 1)
s.set_cell("A2", 3)
s.set_cell("B1", 5)
s.set_cell("B2", 7)
s.set_cell("C1", "=AVG(A1:B2)")
assert s.get_value("C1") == 4.0

# Regression 3: cycle detection still raises CycleError
s = Sheet()
s.set_cell("A1", "=B1")
s.set_cell("B1", "=A1")
try:
    s.get_value("A1")
    assert False, "expected CycleError"
except CycleError:
    pass

# Regression 4: division by zero still raises
s = Sheet()
s.set_cell("A1", "=1/0")
try:
    s.get_value("A1")
    assert False, "expected ZeroDivisionError"
except ZeroDivisionError:
    pass

# Regression 5: precedence/parentheses unchanged
s = Sheet()
s.set_cell("A1", 2)
s.set_cell("B1", 3)
s.set_cell("C1", 4)
s.set_cell("D1", "=A1+B1*C1")
assert s.get_value("D1") == 14.0
s.set_cell("E1", "=(A1+B1)*C1")
assert s.get_value("E1") == 20.0

print("OK")
