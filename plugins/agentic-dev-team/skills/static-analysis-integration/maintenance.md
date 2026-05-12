# Static Analysis Integration — Maintenance Policies

These policies cover the lifecycle of adapters and rulesets shipped with this skill. They are read by maintainers, not by agents at runtime — the runtime skill is in `SKILL.md`.

## Adapter Maintenance Policy

Adapters (SARIF wrappers, bespoke JSON adapters) have a lifecycle independent of the tools they wrap.

- **Owners**: the skill's `maintainers:` frontmatter list. Minimum 2 names.
- **Update trigger**: a tier-2 CI job (nightly) runs each adapter against the installed tool binary. Schema drift that breaks the adapter fails CI and opens an auto-issue tagged `adapter-drift`.
- **Escalation**: a tier-2 failure unassigned for > 14 days escalates to CODEOWNERS.
- **Deprecation**: an adapter failing CI for three consecutive releases AND upstream unmaintained for > 6 months is demoted to "deprecated" — still shipped, emits a warning on invocation, removed in the next MAJOR contract version.
- **Adding a tool**: requires (a) a fixture pair under `evals/static-analysis-tools/tier1-mocks/<tool>/` (mock output + expected unified finding), and (b) a SARIF adapter first; bespoke-JSON only if upstream genuinely has no SARIF plan.

## Ruleset Maintenance Policy

Separate lifecycle from adapters — rulesets track evolving attack patterns, not tool schema drift.

- **Owners**: each custom ruleset (`knowledge/semgrep-rules/*.yaml`) has a `maintainers:` frontmatter block with ≥ 2 names.
- **Review cadence**: quarterly. Reviewers confirm patterns are still relevant, add new attack signatures, retire deprecated ones.
- **FP drift threshold**: if eval fixtures show > 20% false-positive noise on the tier-2 suite, the ruleset is paused and triaged within one release.
- **Community-PR intake**: PRs adding patterns require a positive fixture plus a negative fixture. Rejections must cite the policy.
- **Deprecation**: a ruleset with no review or change in two consecutive review cycles is demoted to "archived" unless a maintainer re-ups.
