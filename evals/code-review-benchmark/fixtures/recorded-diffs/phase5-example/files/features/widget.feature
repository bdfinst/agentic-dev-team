Feature: Widget title rendering
  Synthetic Phase-5-shaped scenario addition (fixture only, see meta.json).

  Scenario: Widget renders a non-empty title
    Given a widget with title "Example"
    When the widget is rendered
    Then the rendered output contains "Example"
