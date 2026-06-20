# Test File Indicators

Canonical list of how to recognize a test file by language. Agents and skills
that need to decide "is this a test?" (for skip logic or for scoping a Farley
Score) cite this file rather than restating the list, so a newly-supported
framework annotation is added in one place.

A `.feature` file always counts as a test file — never skip a target that
contains feature files.

## Indicators by language

| Language | A file is a test when it… |
|---|---|
| **JS/TS** | matches `*.test.*`, `*.spec.*`, or lives inside `__tests__/` |
| **C#** | is a `.cs` file containing `[Fact]`, `[Theory]`, `[Test]`, `[TestCase]`, `[TestMethod]`, or `[TestClass]` |
| **Java** | is a `.java` file containing `@Test`, `@ParameterizedTest`, `@TestFactory`, or a class name ending in `Test`, `Tests`, `TestCase`, or `Spec` |
| **BDD/Gherkin** | is a `.feature` file, or a step-definition file (`*.steps.*`, `*StepDefinitions.*`, `*Steps.*`) |

When a target contains none of the above, an agent scoped to test files
returns its `skip` status.
