# Derived from: wallet/transfer.py::transfer
Feature: Transfer between wallets

  Scenario: Successful transfer moves the amount
    Given wallet "A" holds 100.00 EUR
    And wallet "B" holds 5.00 EUR
    When 40.00 is transferred from "A" to "B"
    Then wallet "A" holds 60.00 EUR
    And wallet "B" holds 45.00 EUR

  Scenario: Transfer of the entire balance
    Given wallet "A" holds 100.00 EUR
    And wallet "B" holds 0.00 EUR
    When 100.00 is transferred from "A" to "B"
    Then wallet "A" holds 0.00 EUR
    And wallet "B" holds 100.00 EUR

  Scenario: Insufficient funds is rejected
    Given wallet "A" holds 10.00 EUR
    And wallet "B" holds 0.00 EUR
    When 40.00 is transferred from "A" to "B"
    Then the transfer fails with "INSUFFICIENT_FUNDS"
    And wallet "A" holds 10.00 EUR
