# Per-language static-analysis setup

User-facing configuration guide for the static-analysis integration: the
build-time self-heal pass that runs at `/build`'s review checkpoints and the
`/code-review` static pre-pass. One section per registered lane, below. This
guide is the single source of truth for the manual setup commands; the
registry of what runs (and how) lives in [`tool-configs.md`](tool-configs.md)
§ Build-time lanes.

## Opting out

Set `DEV_TEAM_STATIC_SELF_HEAL=off` to skip the entire build-time static
self-heal pass — no tool probe or invocation occurs, one info line notes the
skip, and review checkpoints proceed straight to semantic review. Any other
value (or unset) leaves the pass enabled. This mirrors the
`DEV_TEAM_REVIEW_VALUE=off` convention and does not affect `/code-review`'s
full-repo static pre-pass.

## Per-lane section contract

Each language section below is added by the issue that registers its lane
and covers, in order:

1. **Tools and roles** — which tools the lane uses and what each does
   (autofix-capable vs diagnostic-only).
2. **Repo-level install** — how to install them as project-local,
   versioned-with-the-repo dependencies, never user-level/global, so the
   toolchain is reproducible for every contributor and CI.
3. **Configuration** — which config files the tools honor.
4. **Verification** — the lane's detection probe commands, to confirm the
   setup is detected.
5. **Opt-out** — the `DEV_TEAM_STATIC_SELF_HEAL=off` toggle above.
6. **Recognized equivalent providers** — the slot's ordered provider list
   and each provider's qualification status.

Each section also carries a one-line pointer to `/project-init` as the
one-command path to the same repo-level install; this guide remains the
source of truth for the manual commands.

## Python

1. **Tools and roles** — **Ruff** (autofix-capable): lint plus mechanical
   fixes; runs the lane's pre-fix (`ruff check --fix`) and verify
   (`ruff check`). **mypy** (diagnostic-only): type checking; it has no
   autofix — its findings are handed to the coding agent.
2. **Repo-level install** — add both to the project's own dev-dependency
   mechanism so the toolchain is versioned with the repo and reproducible
   for every contributor and CI: `requirements-dev.txt`, a `pyproject.toml`
   dev dependency group, or `python3 -m pip install ruff mypy` inside the
   project venv. Never `pip install --user` or a global pipx install.
3. **Configuration** — Ruff honors the project's `ruff.toml`/`pyproject.toml`
   when present (Ruff's default config discovery — no override flags) and
   falls back to Ruff's defaults; the plugin pins no curated rule set — the
   project owns its quality bar. mypy honors `mypy.ini`/`pyproject.toml`
   (`[tool.mypy]`). A plain `src/`-layout project (modules with no
   `__init__.py`, no mypy package-base config) needs no manual setup
   either — both mypy invocations auto-detect the layout and add
   `--explicit-package-bases` for you; see the mypy Tier 3 entry in
   `tool-configs.md`.
4. **Verification** — the lane's detection probes are `command -v ruff` and
   `command -v mypy`; run them (with the project venv active) to confirm
   the setup will be detected.
5. **Opt-out** — `DEV_TEAM_STATIC_SELF_HEAL=off` skips the build-time
   static self-heal pass entirely (see [Opting out](#opting-out)).
6. **Recognized equivalent providers** — autofix slot: ruff (default,
   last-resort) → black + flake8, qualified only as a combined pair (black
   is the format-autofix half, flake8 the lint-diagnostic half — a partial
   mapping, not 1:1 with ruff's rule surface). Diagnostic slot: mypy
   (default, last-resort) → pyright, gated: recognition requires a ≤ 40 LOC
   Tier 3 adapter in `static-analysis-integration`, which does not exist
   yet. A project arriving with black + flake8 (or pyright) present and
   configured gets them bound; ruff/mypy are installed only into slots that
   bind no recognized provider.

Run `/project-init` for the one-command path to the same repo-level
install; the commands above remain the source of truth for manual setup.

## JS/TS

1. **Tools and roles** — **oxlint** (pin >= 1.0.0; Rust-based,
   ESLint-compatible) is the lane's autofix-capable tool: the mechanical
   pre-fix (`npx oxlint --fix`) covers a subset of its rules — partial
   autofix; findings it cannot fix are reported fast and handed to the coding
   agent — and the verify pass runs oxlint in check mode. **ESLint** is the
   optional deep pass for framework-plugin rules oxlint lacks; it is not part
   of the fast per-step loop (see the provider list below for how an
   ESLint-configured project binds).
2. **Repo-level install**:

   ```bash
   npm install --save-dev oxlint
   ```

   A devDependency pins the oxlint version in `package.json`/the lockfile —
   versioned with the repo and reproducible for every contributor and CI.
   Never `npm install -g oxlint`. One-command alternative: run
   `/project-init` — for a new project its greenfield scaffold installs
   oxlint and wires it as the default linter; for an existing repo it
   installs oxlint only when the slot binds no provider.
3. **Configuration** — oxlint honors `.oxlintrc.json` (ESLint-v8-compatible
   shape; oxlint runs with sensible defaults when no config exists). When
   ESLint coexists as the deep pass, add
   [`eslint-plugin-oxlint`](https://github.com/oxc-project/eslint-plugin-oxlint)
   to the ESLint config to turn off rules oxlint already covers, so the
   ESLint pass only pays for the plugin-only remainder.
4. **Verification**:

   ```bash
   npx --no-install oxlint --version
   ```

   Prints the pinned version when the lane's probe will detect oxlint (the
   probe resolves the project-local `node_modules/.bin` first). Projects
   bound to another provider verify the same way:
   `npx --no-install biome --version` / `npx --no-install eslint --version`.
5. **Opt-out** — `DEV_TEAM_STATIC_SELF_HEAL=off` skips the build-time pass
   (see [Opting out](#opting-out)).
6. **Recognized equivalent providers** (autofix slot; provider semantics live
   in the build skill's `static-self-heal.md`):
   - **oxlint** — default and last-resort provider; full-speed.
   - **biome** — full-speed provider (fast, machine-readable).
   - **eslint** — bound with demotion to slice-boundary granularity only
     (fails the per-step latency budget), with one info line telling the
     user the fast default (oxlint) exists.

## C#

The C# lane rides the .NET SDK — there is no separate linter binary to
install or configure.

1. **Tools and roles**
   - `dotnet format` — autofix-capable: Roslyn-analyzer-driven whitespace,
     style, and analyzer code-fixes. The build-time lane's mechanical
     pre-fix (`whitespace` + `style` at every checkpoint; `analyzers` at the
     slice boundary).
   - Roslyn **ErrorLog SARIF** — diagnostic-only: native SARIF exported by
     the `dotnet build` the TDD loop already runs when passed
     `/p:ErrorLog=results.sarif,version=2.1`. Also the lane's Tier 1
     `/code-review` source.
2. **Repo-level install** — nothing to install: both pieces ship with the
   .NET SDK the project already requires (SDK ≥ 6 for built-in
   `dotnet format`; .NET 5 SDK / Roslyn 3.8+ for the SARIF v2.1 export).
   Where the SDK version matters, pin it repo-level with `global.json`
   (`dotnet new globaljson --sdk-version <version>`) — never a
   user-level/global toolchain assumption. `/project-init` is the
   one-command path: it verifies SDK presence and honors an existing
   `global.json` pin.
3. **Configuration** — the tools honor the project's `.editorconfig`;
   `dotnet format` runs against it at its default `--severity warn`.
   Third-party Roslyn analyzers (StyleCop.Analyzers, SonarAnalyzer.CSharp,
   …) are added as `PackageReference`s in the `.csproj` and automatically
   ride the same ErrorLog SARIF.
4. **Verification** — the lane's detection probe is `command -v dotnet`
   (one SDK probe covers both tools). Confirm the pieces work:

   ```bash
   command -v dotnet
   dotnet format --version
   dotnet build /p:ErrorLog=results.sarif,version=2.1   # writes results.sarif
   ```

5. **Opt-out** — set `DEV_TEAM_STATIC_SELF_HEAL=off` to skip the build-time
   self-heal pass entirely (see [Opting out](#opting-out) above).
6. **Recognized equivalent providers** — none. `dotnet format` is
   SDK-builtin, and analyzer alternatives join via the `.csproj`, not via
   lane providers.

## Java

Registered by #810.

### Tools and roles

- **PMD** — **diagnostic-only** (no autofix tool exists for a tight
  per-step loop in Java). Syntax-tree based, so it needs no compile step:
  fast enough for build-time checkpoints, and its native SARIF renderer
  makes it a zero-adapter `/code-review` source. Findings go to the coding
  agent to fix; PMD re-runs to confirm convergence.

### Repo-level install

From your project root (requires a JDK/JRE — `java` on PATH):

```bash
python3 scripts/install-java-static-analysis.py
```

Installs a pinned PMD distribution into the repo-local **`.pmd/`**
directory (`PMD_INSTALL_DIR` overrides the target). Add `.pmd/` to your
project's `.gitignore` — the distribution is large and must never be
committed; the installer prints a reminder when the entry is missing. No
PATH change is needed, and never install user-level/global. Re-running is
idempotent: an existing install is detected and nothing is re-downloaded.

Or run `/project-init` — the one-command path to the same repo-level
install.

### Configuration

- **Repo-root `pmd-ruleset.xml`**, when present, is used by both the
  build-time lane and the `/code-review` pass. Carry your own
  `<exclude-pattern>` entries in it (generated-output dirs like `target/`).
- Otherwise the plugin's quickstart-wrapping default ruleset applies —
  PMD's quickstart rules plus excludes for `target/`, `build/`, `out/`,
  and `.gradle/`. Test sources run the same rules as production code.

### Verification

Confirm the setup is detected (repo-local probe first, then PATH):

```bash
ls .pmd/pmd-bin-*/bin/pmd     # repo-local launcher (checked first)
command -v pmd                # PATH fallback
.pmd/pmd-bin-*/bin/pmd --version
```

### Opt-out

Set `DEV_TEAM_STATIC_SELF_HEAL=off` to skip the build-time pass entirely —
see [Opting out](#opting-out).

### Recognized equivalent providers

Diagnostic slot, in order: **PMD** (default, last-resort) → **checkstyle**.
checkstyle qualifies as Tier 1 via native SARIF output (Checkstyle ≥ 10.3,
no adapter); a project arriving with a repo-root `checkstyle.xml` binds it
and PMD is not installed. SpotBugs is not a provider candidate — it needs
compiled bytecode and belongs at the end-of-build `/code-review` pass only.
