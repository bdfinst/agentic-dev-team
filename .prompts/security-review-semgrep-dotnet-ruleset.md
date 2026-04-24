You are working in the `agentic-security-review` plugin at
/Users/finsterb/_git-os/agentic-dev-team/plugins/agentic-security-review/

Your task: fix the broken semgrep `p/dotnet` registry reference and
pin a working C# ruleset bundle so .NET repositories receive
meaningful static analysis coverage out of the box. Today the plugin's
default semgrep invocation fails on .NET repos with a 404 against the
semgrep registry, and sub-agents have to improvise their way around
it — which means coverage depends on whoever is running the pipeline,
not on the plugin.

## Evidence

Observed across the 2026-04-24 runs on /Users/finsterb/_git-aci/ng-security-scan:

- extranetapi run closing note: "semgrep p/dotnet ruleset 404s at
  the registry."
- speedpay-sdk run: "semgrep (0 C# hits — rule coverage thin)."
- ivr run: the sub-agent improvised by running
  `semgrep --config=p/csharp+p/secrets+p/owasp-top-ten` to fill the
  gap. This worked, but only because that sub-agent was careful; a
  sub-agent that takes the skill at face value will run with no C#
  rules at all.
- **admintool-api (Node.js + TypeScript) run closing note: "Semgrep
  `p/express` returned HTTP 404 from the registry and was dropped;
  remaining semgrep packs (typescript/nodejs/owasp-top-ten/secrets/
  sql-injection/command-injection/xss/jwt/dockerfile) produced only
  the Dockerfile `USER root` match — the heavy lifting here was
  business-logic reasoning, not SAST."** — confirms the problem is
  not limited to .NET. `p/express` is another pack this plugin
  references that no longer resolves.

The semgrep registry at https://semgrep.dev/r does not currently host
a pack under the ID `p/dotnet` or `p/express` (both 404). The working
replacements identified by live-testing:

- `p/csharp` (sometimes listed as `r/csharp`) — replaces `p/dotnet`
- `p/nodejsscan` or `p/nodejs` — replaces `p/express`
- `p/secrets`, `p/owasp-top-ten`, `p/findsecbugs-rules` — useful
  cross-cutting companions independent of language

## Fix direction

Three things to do in one PR:

### 1. Replace the broken pack references with working ones

Grep for `p/dotnet` and replace with `p/csharp`. Grep for `p/express`
and replace with `p/nodejsscan` (or `p/nodejs`, whichever is current
on the registry when you check — verify with a live fetch first).
Apply across:

- `skills/security-assessment-pipeline/SKILL.md`
- `commands/security-assessment.md`
- `agents/exec-report-generator.md` (if referenced in "Coverage-gap
  callouts")
- Any Phase-1 tool-dispatch documentation
- `CHANGELOG.md` entry for the fix

### 2. Add a documented .NET scanner invocation matching the Java pattern

The plugin already has a language-specific SAST wrapper for Java at
`tests/` / `harness/` (check the current structure). The .NET
equivalent should follow the same pattern.

Reference shape (adapted from the NextGen driver's `scan_java.sh`
at /Users/finsterb/_git-aci/ng-security-scan/scripts/scan_java.sh —
read-only reference; do not copy the file wholesale, just match
the shape):

```bash
#!/usr/bin/env bash
# scan_dotnet.sh — .NET-specific SAST pass.
#
# Runs semgrep with p/csharp + p/secrets + p/owasp-top-ten.
# Outputs SARIF to <memory-dir>:
#   semgrep-csharp-<slug>.sarif
#
# No-op when no .cs files are present.
```

Emit SARIF only (not JSON), per the unified-finding envelope's
SARIF-first ingestion path. Dedup against the plugin's generic
semgrep pass via the existing cross-tool priority dedup in
`static-analysis-integration`.

Acceptance:

- [ ] New `scripts/scan_dotnet.sh` (or similarly-named helper
  following the plugin's existing convention).
- [ ] Invoked from the Phase 1 tool fan-out where the current
  `p/dotnet` reference lives.
- [ ] No-op on non-.NET repos.
- [ ] SARIF output landing in `memory/semgrep-csharp-<slug>.sarif`.

### 3. Pin a known-good semgrep ruleset manifest

Today each run reaches out to the semgrep registry live. Registry
availability and pack identity drift over time; today's `p/csharp`
might be moved to `r/csharp/v2` tomorrow. Mitigate:

- Add `knowledge/semgrep-rulesets.yaml` listing each pack the
  plugin depends on, with:
  - canonical name (`p/csharp`, `p/secrets`, `p/owasp-top-ten`,
    `p/java`, etc.)
  - purpose (one-line)
  - fallback (e.g., `r/csharp` if `p/csharp` 404s)
- Have scan_dotnet.sh (and the sibling scan_java.sh) consult this
  file rather than inline-hardcoding the pack IDs.
- Document a smoke-test script under `tests/` that fetches each
  pack and asserts the registry returns non-empty rule counts —
  catches the p/dotnet-style regression before it hits a real run.

Acceptance:

- [ ] `knowledge/semgrep-rulesets.yaml` committed.
- [ ] `scan_dotnet.sh` and the existing `scan_java.sh` (if it
  lives in this plugin; the NextGen driver's copy is a reference
  only) consult the yaml.
- [ ] Smoke test validates pack-ID health against the registry.

## Acceptance — end-to-end

- [ ] No `/security-assessment` run against a .NET repo produces
  a closing note like "semgrep p/dotnet 404" or "0 C# hits — rule
  coverage thin."
- [ ] Running against a known .NET repo (try
  `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/ivr` —
  small, representative, and has a known positive corpus from the
  2026-04-24 baseline) surfaces at least the following rule classes:
  - hardcoded-credential (p/secrets — we KNOW `endavauser/Jupiter2020$`
    is in that repo's `appsettings.Development.json`; if the new
    invocation misses it, something is wrong)
  - xxe / insecure-deserialization (p/csharp — baseline run identified
    a `BinaryFormatter` call in ivr)
  - insecure-transport (p/csharp — `SkipCertValidation=true` lands here)
- [ ] Regression: non-.NET repos still get their appropriate scanners
  (p/javascript, p/python, etc.) — check `scan_java.sh` and any
  sibling wrappers still run on their own ecosystems.
- [ ] `CHANGELOG.md` entry: "Fixed semgrep p/dotnet 404 by switching
  to p/csharp + adding scan_dotnet.sh wrapper + externalizing
  ruleset manifest to knowledge/."

## Non-goals

- Do NOT write new semgrep rules in this PR. The gap is registry
  pack reference, not rule authorship. Custom rules are a separate
  conversation and live under `knowledge/semgrep-rules/` when they
  happen.
- Do NOT replace semgrep with a different SAST engine. Tool-first
  posture is load-bearing for this plugin.
- Do NOT make the scanner invocation network-optional (i.e.,
  vendored packs) in this PR — that's a legitimate follow-up but a
  bigger lift. Document it as a TODO in the new scan_dotnet.sh
  header.

## Definition of done

- PR against the `agentic-security-review` plugin.
- CI passes.
- Post-merge smoke test against
  `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/ivr`:
  the resulting `memory/semgrep-csharp-ivr.sarif` has a non-zero
  result count and includes the `endavauser/Jupiter2020$` hit
  (baseline truth) plus the `BinaryFormatter` hit.
