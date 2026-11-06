Feature: Sum CLI

  Scenario: The CLI prints the sum of its arguments
    Given the arguments "4" and "6"
    When the CLI runs
    Then it prints "sum=10"
