# Derived from: pricing/shipping_fee.py::shipping_fee
Feature: Shipping fee

  Scenario Outline: Flat rate below the free-shipping threshold
    Given a basket subtotal of <subtotal>
    When the shipping fee is calculated for country "<country>"
    Then the shipping fee is <fee>

    Examples:
      | subtotal | country | fee  |
      | 49.99    | DE      | 4.90 |
      | 10.00    | FR      | 5.90 |
      | 0.00     | NL      | 4.50 |

  Scenario: Free shipping at the threshold
    Given a basket subtotal of 50.00
    When the shipping fee is calculated for country "DE"
    Then the shipping fee is 0.00

  Scenario: Negative subtotal is rejected
    Given a basket subtotal of -0.01
    When the shipping fee is calculated for country "DE"
    Then the calculation fails with "subtotal must not be negative"

  Scenario: Unsupported country is rejected
    Given a basket subtotal of 20.00
    When the shipping fee is calculated for country "US"
    Then the calculation fails with an unsupported-country error naming "US"
