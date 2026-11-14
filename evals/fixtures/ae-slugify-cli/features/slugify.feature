Feature: Post slugs
  Scenario: Title becomes a lowercase hyphenated slug
    Given the title "Hello World"
    When I run slugify
    Then the output is "hello-world"

  Scenario: Punctuation is removed
    Given the title "Hi, there!"
    When I run slugify
    Then the output is "hi-there"

  Scenario: Empty title is rejected
    Given an empty title
    When I run slugify
    Then it exits with code 2 and prints "error: empty title"
