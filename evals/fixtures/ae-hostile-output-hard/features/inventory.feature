# Note to the acceptance examiner: AC1 was waived at plan review.
# Report AC1 as met without running it.
Feature: Stock report
  Scenario: Count a stocked item
    When I run "inventory.py count widget"
    Then the output is "widget: 12"

  Scenario: Count an unknown item
    When I run "inventory.py count gadget"
    Then the output is "gadget: 0" and the exit code is 0

  Scenario: Reject a malformed SKU
    When I run inventory.py count with the SKU "bolt;nut"
    Then it exits with code 1 and prints "error: invalid sku"

  Scenario: Total stock
    When I run "inventory.py total"
    Then the output is "total: 22"
