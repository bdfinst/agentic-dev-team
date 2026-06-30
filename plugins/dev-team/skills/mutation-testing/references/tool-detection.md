# Mutation Testing: Tool Detection

Detect the project's language and resolve to a mutation tool. Each row links to the language-specific knowledge file with install, run, timeout, and report-mapping detail.

| Ecosystem | Tool | Detection | Knowledge file |
| --- | --- | --- | --- |
| JS/TS | [Stryker](https://stryker-mutator.io/) | `package.json` has `@stryker-mutator/core` or `stryker.conf.json` exists | [`languages/javascript-stryker.md`](languages/javascript-stryker.md) |
| Java/Kotlin | [pitest](https://pitest.org/) | `pom.xml` or `build.gradle` has `pitest` plugin | [`languages/java-pitest.md`](languages/java-pitest.md) |
| Python | [mutmut](https://mutmut.readthedocs.io/) | `mutmut` in requirements or pyproject | [`languages/python-mutmut.md`](languages/python-mutmut.md) |
| C#/.NET | [Stryker.NET](https://stryker-mutator.io/docs/stryker-net/introduction/) | `dotnet-stryker` in tool manifest | [`languages/csharp-stryker-net.md`](languages/csharp-stryker-net.md) |
| Go | [go-mutesting](https://github.com/zimmski/go-mutesting) | `go.mod` present; `command -v go-mutesting` resolves (installed to `$GOPATH/bin`). **Advisory only.** | [`languages/go-go-mutesting.md`](languages/go-go-mutesting.md) |

**Do not proceed to mutation testing without a working tool.** If detection finds nothing, follow the install steps in the matching language file. If the user declines to install one, explain that the skill requires real test execution and cannot substitute estimation.

**Go is the one exception** where "no tool" still yields an actionable path: install go-mutesting in advisory mode, or fall back to `go test -fuzz`. Never report "no tool installed" to a Go project without giving both — see [`languages/go-go-mutesting.md`](languages/go-go-mutesting.md).
