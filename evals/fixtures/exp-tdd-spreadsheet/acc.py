from sheet import Sheet, CycleError

# Scenario 1: literal value
s = Sheet()
s.set_cell("A1", 5)
assert s.get_value("A1") == 5.0
assert isinstance(s.get_value("A1"), float)
assert s.get_raw("A1") == 5

# Scenario 2: empty cell is 0
s = Sheet()
assert s.get_value("Z9") == 0.0
assert s.get_raw("Z9") is None

# Scenario 3: simple arithmetic formula
s = Sheet()
s.set_cell("A1", 2)
s.set_cell("B2", 3)
s.set_cell("C1", "=A1+B2")
assert s.get_value("C1") == 5.0
assert s.get_raw("C1") == "=A1+B2"

# Scenario 4: precedence and parentheses
s = Sheet()
s.set_cell("A1", 2)
s.set_cell("B1", 3)
s.set_cell("C1", 4)
s.set_cell("D1", "=A1+B1*C1")
assert s.get_value("D1") == 14.0
s.set_cell("E1", "=(A1+B1)*C1")
assert s.get_value("E1") == 20.0

# Scenario 5: chained references
s = Sheet()
s.set_cell("A1", "=B1")
s.set_cell("B1", "=C1")
s.set_cell("C1", 7)
assert s.get_value("A1") == 7.0

# Scenario 6: SUM over a range
s = Sheet()
s.set_cell("A1", 1)
s.set_cell("A2", 2)
s.set_cell("A3", 3)
s.set_cell("B1", "=SUM(A1:A3)")
assert s.get_value("B1") == 6.0

# Scenario 7: AVG over a rectangle
s = Sheet()
s.set_cell("A1", 1)
s.set_cell("A2", 3)
s.set_cell("B1", 5)
s.set_cell("B2", 7)
s.set_cell("C1", "=AVG(A1:B2)")
assert s.get_value("C1") == 4.0
# reversed corners equal the same rectangle
s.set_cell("C2", "=SUM(B2:A1)")
assert s.get_value("C2") == 16.0
# AVG with one empty cell counts it as 0
s2 = Sheet()
s2.set_cell("A1", 2)
s2.set_cell("A2", 4)
s2.set_cell("B1", 6)
# B2 empty
s2.set_cell("C1", "=AVG(A1:B2)")
assert s2.get_value("C1") == 3.0  # (2+4+6+0)/4

# Scenario 8: cycle detection
s = Sheet()
s.set_cell("A1", "=B1")
s.set_cell("B1", "=A1")
try:
    s.get_value("A1")
    assert False, "expected CycleError"
except CycleError:
    pass
s = Sheet()
s.set_cell("A1", "=A1")
try:
    s.get_value("A1")
    assert False, "expected CycleError on self-reference"
except CycleError:
    pass

# Scenario 9: division by zero
s = Sheet()
s.set_cell("A1", "=1/0")
try:
    s.get_value("A1")
    assert False, "expected ZeroDivisionError"
except ZeroDivisionError:
    pass
s = Sheet()
s.set_cell("A1", "=5/B9")  # B9 empty -> 0
try:
    s.get_value("A1")
    assert False, "expected ZeroDivisionError dividing by empty cell"
except ZeroDivisionError:
    pass

print("OK")
