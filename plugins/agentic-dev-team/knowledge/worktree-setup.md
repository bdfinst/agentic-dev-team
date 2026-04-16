# Worktree Setup Reference

Language/framework detection for dependency installation in git worktrees. Used by the implementer subagent before starting TDD.

## Detection Table

Check for indicator files in the order listed. First match wins.

| Indicator File | Language/Framework | Install Command | Test Command |
|---|---|---|---|
| package-lock.json | Node.js (npm) | `npm ci` | `npm test` |
| yarn.lock | Node.js (yarn) | `yarn install` | `yarn test` |
| pnpm-lock.yaml | Node.js (pnpm) | `pnpm install` | `pnpm test` |
| bun.lockb | Node.js (bun) | `bun install` | `bun test` |
| package.json (no lockfile) | Node.js (npm fallback) | `npm install` | `npm test` |
| requirements.txt | Python | `pip install -r requirements.txt` | `pytest` |
| pyproject.toml | Python | `pip install -e .` | `pytest` |
| go.mod | Go | `go mod download` | `go test ./...` |
| Cargo.toml | Rust | `cargo build` | `cargo test` |
| pom.xml | Java (Maven) | `mvn install -DskipTests` | `mvn test` |
| build.gradle / build.gradle.kts | Java (Gradle) | `gradle build -x test` | `gradle test` |
| *.csproj / *.sln | .NET | `dotnet restore` | `dotnet test` |

## Notes

- **Detection uses file presence only** -- check in the order listed above. First match wins. This resolves conflicting lockfile scenarios (e.g., a project with both package-lock.json and yarn.lock uses npm because package-lock.json appears first).
- **No recognized files found**: Skip setup with a warning. Proceed to implementation without dependency installation.
- **Install fails**: Return BLOCKED with the full error output. Do not attempt to diagnose or fix dependency installation failures.
- **Baseline tests fail**: Return BLOCKED with the test output. Do not attempt to fix pre-existing test failures -- they are outside the scope of the current task.
