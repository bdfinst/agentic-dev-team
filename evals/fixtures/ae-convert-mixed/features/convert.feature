Feature: Temperature conversion
  Scenario: Celsius to Fahrenheit
    When I run "convert.py --to f 100"
    Then the output is "212.0"

  Scenario: Fahrenheit to Celsius
    When I run "convert.py --to c 32"
    Then the output is "0.0"

  Scenario: Bad arguments
    When I run "convert.py --to k 10"
    Then it exits with code 64
