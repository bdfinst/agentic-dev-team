You are working in the `agentic-security-review` plugin at
/Users/finsterb/_git-os/agentic-dev-team/plugins/agentic-security-review/

Your task: make the fp-reduction joern path actually build CPGs for
.NET repositories. Today every .NET target falls back to LLM mode —
which degrades FP-reduction quality for what is probably the most
common target ecosystem the plugin sees in enterprise use.

## Evidence

Observed across four separate `/security-assessment` runs on
2026-04-24 (extranetapi, login-service, speedpay-sdk, ivr — all .NET
repos in /Users/finsterb/_git-aci/ng-security-scan). Every run's
closing notes said the same thing. Representative quotes:

- "FP-reduction used the LLM-fallback path because no joern CPG was
  built for this .NET solution" (speedpay-sdk)
- "joern unavailable so FP-reduction reachability used LLM fallback"
  (extranetapi)

The fp-reduction skill explicitly promises this pathway:

  skills/false-positive-reduction/SKILL.md:3 — "Hybrid FP-reduction
  skill — joern call-graph when present, LLM fallback when absent."

But the reachability wrapper at
`skills/false-positive-reduction/tools/reachability.sh:44` invokes
`joern-parse "$REPO" --output "$CPG_PATH"` with no `--language`
argument, and the plugin install scripts do not install joern or
its C# frontend.

Result: `command -v joern-parse` succeeds on developer machines that
happened to install joern for JS/Python/Java — but CPG build fails
for .NET because joern defaults to language autodetect and the C#
frontend is not part of the default joern distribution (it ships as
a separate Scala module or via `joern-cli-extras`).

## Fix direction

Two independent things to fix — do both in one PR:

### (a) Install-time: ensure joern + C# frontend are set up

- Update `install.sh` and `install-macos.sh` to (i) check for joern,
  (ii) if absent, either install it or print a clear "joern not
  available — fp-reduction will run in LLM-fallback mode" warning
  with a link to joern's install docs.
- Install the joern C# / C frontends explicitly. At the time of
  writing, joern's C# parser is driven by `c2cpg.sh --language csharp`
  or the more modern `dotnetastgen` bridge. Confirm which is current
  in joern's latest release and install it. Document the minimum
  joern version tested.
- Install-time verification step: run `joern-parse --language csharp
  --output /tmp/test.cpg <a tiny fixture .cs file>` and confirm
  non-zero output. Fail the install script with a clear message if
  the verification fails. Document at least one fixture .cs file
  under `knowledge/fixtures/joern-dotnet/` that the verification
  step uses.

### (b) Runtime: detect .NET and pass `--language csharp` to joern

- Extend `tools/reachability.sh` to detect the target's primary
  language:
  - `.cs` / `.csproj` / `.sln` present → `--language csharp`
  - `.ts` / `.tsx` / `.js` / `package.json` → `--language javascript`
  - `.py` / `pyproject.toml` / `requirements.txt` → `--language python`
  - `.java` / `pom.xml` / `build.gradle` → `--language javasrc`
  - `.go` / `go.mod` → `--language gosrc`
  - Otherwise → let joern autodetect (current behavior).
- Preserve the existing cache-by-commit-SHA semantics at the top of
  the script; only the `joern-parse` invocation changes.
- Preserve the existing exit-code contract: 0 = CPG built, 1 = joern
  absent, 2 = build failed. This is load-bearing; the fp-reduction
  agent branches on it.
- Add a language-tag to the cache file name so cross-language test
  fixtures don't collide: `<sha>.<language>.cpg`.

## Acceptance

- [ ] `tools/reachability.sh` correctly classifies a .NET repo and
  invokes joern with `--language csharp`.
- [ ] Install scripts install joern + C# frontend or emit a clear,
  actionable "fp-reduction will degrade to LLM-fallback" warning.
- [ ] Running `/security-assessment` against a known .NET repo
  (e.g., `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/ivr`)
  produces a disposition register whose entries carry
  `reachability_tool: joern-cpg`, NOT `llm-fallback`.
- [ ] The `exec-report-generator` section "Coverage-gap callouts"
  no longer lists "joern CPG not built" for .NET targets (this note
  is currently hardcoded into the report's Section 6).
- [ ] Regression: re-running against a non-.NET repo (e.g., a Node
  or Python repo) still picks the right language and still produces
  `reachability_tool: joern-cpg`.
- [ ] Fallback still works: if joern-parse fails for a .NET repo
  (malformed solution, unsupported target framework), reachability.sh
  exits 2 and the caller logs a structured reason rather than
  crashing.

## Non-goals

- Do NOT remove the LLM-fallback path. It is the intended safety
  net and is used when joern is simply not installed on the scan
  machine. The plugin's value proposition is hybrid; this work just
  makes the "hybrid when available" half actually fire for .NET.
- Do NOT add a new shipped-with-plugin joern binary. Installing a
  Scala+JVM toolchain as part of the plugin install is a big ask;
  the right pattern is detect-and-report, with install-guidance for
  the operator.
- Do NOT rewrite the fp-reduction agent. It already consumes the
  CFG JSON correctly — the gap is upstream of the agent.

## Hint — ground-truth behavior for the test fixture

Put a 20-line .cs file in `knowledge/fixtures/joern-dotnet/` with a
known source → sink chain (e.g., an HTTP request handler that
concatenates user input into a SQL command string). Run the existing
`/security-assessment` pipeline against the fixture directory. With
joern wired correctly, the disposition for the SQLi finding must
show `reachability_trace` referencing specific node IDs from the
CPG (indicating joern ran), not an LLM-generated narrative. Use
this as the end-to-end test.

## Definition of done

- PR against `agentic-security-review` plugin.
- CI passes.
- Re-run `/security-assessment` against
  `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/login-service`
  as a post-merge smoke test; confirm the disposition register now
  has `reachability_tool: joern-cpg` (or `joern-cpg` at the register
  level with individual overrides only where joern legitimately
  failed on a specific subproject).
