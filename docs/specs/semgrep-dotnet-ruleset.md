# Spec: Semgrep ruleset fix for .NET (and Node) targets

Source prompt: [`.prompts/security-review-semgrep-dotnet-ruleset.md`](../../.prompts/security-review-semgrep-dotnet-ruleset.md)
Target plugin: `plugins/agentic-security-review/`

## Intent Description

The plugin's default semgrep invocation for .NET repositories references the registry pack `p/dotnet`, which 404s. A parallel problem affects Node/TypeScript scans via a broken `p/express` reference. When either 404 occurs, sub-agents either (a) silently produce thin coverage or (b) improvise a replacement ruleset on the fly. Both outcomes destroy reproducibility — plugin coverage depends on whoever happens to be running the pipeline rather than on the plugin itself.

This change fixes the registry references, introduces a `.NET`-specific scanner wrapper matching the existing Java pattern, and externalizes the list of semgrep packs to a manifest file so that future registry drift is caught by a smoke test rather than by a degraded scan. The plugin's tool-first posture (semgrep, not LLM-improvised rules) is preserved throughout; the change is about making that posture actually fire.

## User-Facing Behavior

```gherkin
Feature: Semgrep ruleset coverage for .NET and Node targets

  Scenario: Security assessment against a .NET repo produces non-empty C# SAST coverage
    Given a target .NET repository with known vulnerable patterns
    When I run /security-assessment against the target
    Then memory/semgrep-csharp-<slug>.sarif exists with a non-zero result count
    And no closing note mentions "p/dotnet 404" or "0 C# hits"
    And hardcoded-credential, insecure-deserialization, and insecure-transport rule classes are represented in the SARIF output

  Scenario: Security assessment against a Node/TypeScript repo produces non-empty JS/TS SAST coverage
    Given a target Node/TypeScript repository
    When I run /security-assessment against the target
    Then the semgrep SARIF output has a non-zero result count
    And no closing note mentions "p/express 404"

  Scenario: scan_dotnet.sh no-ops on a non-.NET target
    Given a target directory that contains no .cs files
    When scan_dotnet.sh runs against the target
    Then scan_dotnet.sh produces no SARIF output
    And scan_dotnet.sh exits successfully

  Scenario: scan_dotnet.sh emits SARIF-only output
    Given a target .NET repository with at least one .cs file
    When scan_dotnet.sh runs against the target
    Then scan_dotnet.sh writes SARIF to memory/semgrep-csharp-<slug>.sarif
    And scan_dotnet.sh does not write JSON output
    And the SARIF output conforms to the unified-finding envelope ingestion path

  Scenario: Ruleset manifest drives pack selection
    Given knowledge/semgrep-rulesets.yaml lists the packs and fallbacks
    When scan_dotnet.sh (or scan_java.sh) runs
    Then the script reads the pack list from the manifest
    And no pack ID is hardcoded inline in the script

  Scenario: Fallback pack is used when the canonical pack 404s
    Given knowledge/semgrep-rulesets.yaml declares p/csharp with fallback r/csharp
    And the registry returns 404 for p/csharp
    When scan_dotnet.sh runs
    Then scan_dotnet.sh retries with the fallback r/csharp
    And the scan completes successfully

  Scenario: Smoke test catches registry drift before a real run
    Given the ruleset smoke test is run in CI
    When any pack listed in knowledge/semgrep-rulesets.yaml returns 0 rules or 404
    Then the smoke test fails
    And the failure message names the offending pack and its fallback (if any)

  Scenario: Cross-tool dedup against the generic semgrep pass
    Given the generic semgrep pass and scan_dotnet.sh both run on the same .NET repo
    When findings are aggregated
    Then duplicate findings are deduplicated via the existing cross-tool priority dedup in static-analysis-integration
    And no finding is double-counted in the disposition register

  Scenario: Non-.NET ecosystems still run their appropriate scanners
    Given a target Python repository
    When /security-assessment runs
    Then the Python scanner wrapper (p/python or equivalent) still runs
    And scan_dotnet.sh produces no output
```

## Architecture Specification

**Components modified**

- `skills/security-assessment-pipeline/SKILL.md` — replace `p/dotnet` with `p/csharp`; replace `p/express` with the current Node equivalent (verify live).
- `commands/security-assessment.md` — same pack-reference replacement.
- `agents/exec-report-generator.md` — update "Coverage-gap callouts" if it references the old pack IDs.
- Phase-1 tool-dispatch documentation (wherever that lives) — same replacement.
- `CHANGELOG.md` — entry describing the fix.

**Components added**

- `scripts/scan_dotnet.sh` — .NET-specific SAST wrapper following the shape of the NextGen driver's `scan_java.sh` (reference only; do not copy wholesale). Emits SARIF-only to `memory/semgrep-csharp-<slug>.sarif`. No-op on non-.NET repos. Reads its pack list from the manifest. Header documents a TODO for future vendored/offline packs.
- `knowledge/semgrep-rulesets.yaml` — canonical manifest listing every pack the plugin depends on with fields: `name`, `purpose` (one line), `fallback` (optional). Consumed by `scan_dotnet.sh` and the sibling `scan_java.sh` if it lives in this plugin.
- `tests/scripts/semgrep-rulesets-smoke-test.*` — smoke test that fetches each pack from the registry and asserts non-zero rule count. Runs in CI.

**Key interfaces**

- `scan_dotnet.sh` contract:
  - Inputs: `<target-dir>`, `<slug>`, `[<memory-dir>]`
  - Output: `<memory-dir>/semgrep-csharp-<slug>.sarif` (or no output if no `.cs` files)
  - Exit: 0 on success (including no-op); non-zero on scan failure
- Manifest schema (`knowledge/semgrep-rulesets.yaml`):
  ```yaml
  packs:
    - name: p/csharp
      purpose: ".NET static analysis baseline"
      fallback: r/csharp
    - name: p/secrets
      purpose: "Credential leak detection"
  ```

**Constraints**

- SARIF-only output to align with the unified-finding envelope's SARIF-first ingestion path.
- Dedup must go through the existing cross-tool priority dedup in `static-analysis-integration`; do not introduce a parallel dedup.
- Tool-first posture preserved — no new semgrep rules authored in this PR; only pack references and wrapper infrastructure.
- Vendored/offline packs are out of scope for this PR but documented as a TODO in the `scan_dotnet.sh` header.
- Do NOT replace semgrep with a different SAST engine.

**Scope note** — this spec bundles three logical slices:
1. Pack-reference replacement (1-line greps in multiple files)
2. `scan_dotnet.sh` wrapper + invocation from Phase 1
3. Manifest externalization + smoke test

Slice 1 alone would technically resolve the 404s but leaves the improvisation problem unaddressed. Slice 3 is the reproducibility guardrail. All three are bundled because they share the end-to-end acceptance test (a .NET scan producing non-zero C# SARIF against the ivr baseline). Splitting is possible; the human explicitly chose to bundle.

## Acceptance Criteria

- [ ] No occurrence of `p/dotnet` remains in the plugin source after the fix (verified by grep).
- [ ] No occurrence of `p/express` remains in the plugin source after the fix (verified by grep).
- [ ] Replacement pack IDs (`p/csharp`, current Node equivalent) are live-verified against the semgrep registry at fix time.
- [ ] `scripts/scan_dotnet.sh` exists, is executable, and is invoked from Phase 1 where the old `p/dotnet` reference lived.
- [ ] `scripts/scan_dotnet.sh` no-ops on a target containing no `.cs` files.
- [ ] `scripts/scan_dotnet.sh` emits SARIF only to `memory/semgrep-csharp-<slug>.sarif`.
- [ ] `knowledge/semgrep-rulesets.yaml` exists with one entry per pack the plugin depends on, including `name`, `purpose`, optional `fallback`.
- [ ] `scan_dotnet.sh` and `scan_java.sh` (if hosted in this plugin) read their pack list from the manifest; no inline hardcoded pack IDs remain.
- [ ] CI smoke test fetches every pack in the manifest and fails on 404 or empty rule count, naming the offending pack.
- [ ] Running `/security-assessment` against `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/ivr` produces `memory/semgrep-csharp-ivr.sarif` containing:
  - the `endavauser/Jupiter2020$` credential in `appsettings.Development.json` (baseline truth from 2026-04-24)
  - the `BinaryFormatter` insecure-deserialization finding
  - at least one insecure-transport finding (`SkipCertValidation=true`)
- [ ] No `/security-assessment` closing note contains "semgrep p/dotnet 404", "0 C# hits — rule coverage thin", or "p/express 404".
- [ ] Regression: running against a non-.NET repo still invokes its native scanner (Python, JS, Java, etc.) and still produces SARIF output where applicable.
- [ ] `CHANGELOG.md` entry: "Fixed semgrep p/dotnet 404 by switching to p/csharp + adding scan_dotnet.sh wrapper + externalizing ruleset manifest to knowledge/."
- [ ] Post-merge smoke test against `ivr` confirms non-zero `memory/semgrep-csharp-ivr.sarif` result count.

## Consistency Gate

- [x] Intent is unambiguous — the 404s are the root cause; fix is live-verified pack IDs plus a manifest + wrapper to make the fix stick
- [x] Every behavior in the intent has at least one corresponding BDD scenario
- [x] Architecture specification constrains implementation to what the intent requires
- [x] Concepts named consistently (`semgrep-csharp-<slug>.sarif`, `p/csharp`, `scan_dotnet.sh`, `knowledge/semgrep-rulesets.yaml`)
- [x] No artifact contradicts another

**Scope note**: three logical slices bundled deliberately. If the three-slice scope proves too large during planning, the suggested split order is (1) pack rename + manifest, (2) scan_dotnet.sh wrapper, (3) smoke test — in that order, because each layer depends on the prior.

**Verdict: PASS** — spec is ready for planning, with an explicit flag that the human should revisit scope at plan time if any slice reveals unexpected complexity.
