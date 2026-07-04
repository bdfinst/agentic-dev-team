# Plan — #810: Java static-analysis lane (PMD)

## Goal

Register the Java lane of `/build`'s static self-heal pass and add PMD as a
Tier 1 `/code-review` SARIF source, supplying only the Java tool facts —
invocations, ruleset resolution, tier placement, install pinning, and the
provider list. The mechanism (scoping, lanes, the shared fix loop, the
2-attempt cap, detection ladder, granularity, ordering, the
`DEV_TEAM_STATIC_SELF_HEAL=off` opt-out) is #811's and is not restated or
modified.

## Acceptance criteria (from the issue)

1. `scripts/install-java-static-analysis.py` — Python 3.8+ stdlib-only;
   installs the pinned PMD into repo-local `.pmd/` (or `PMD_INSTALL_DIR`);
   re-run exits 0 without re-downloading; `java` absent → exit 1.
2. `.pmd/` gitignored in this repo; installer prints an add-to-gitignore
   reminder (no silent mutation).
3. Version pin in exactly one place (the `PMD_VERSION` constant).
4. `scripts/dev-setup.sh` warn-only `pmd` presence check naming the
   installer; exit code unaffected by absence.
5. Java lane row in the "Build-time lanes" registry: diagnostic-only,
   `*.java`, repo-local-first probe, `--file-list` + `-f json` invocation,
   empty-set skip and exit-code-4 wrapper contracts.
6. PMD Tier 1 entry in `static-analysis-integration/SKILL.md` +
   `references/tool-configs.md`: native SARIF, no adapter,
   language-conditional dispatch and hinting.
7. Ruleset resolution (repo-root `pmd-ruleset.xml` else the plugin's
   quickstart-wrapping default) documented and identical for both
   invocations.
8. Default ruleset ships `<exclude-pattern>` entries for `target/`,
   `build/`, `out/`, `.gradle/`; custom rulesets carry their own.
9. Provider list PMD → checkstyle with checkstyle's Tier 1 qualification
   (native SARIF, Checkstyle ≥ 10.3) recorded.
10. Java section added to `references/language-setup.md` per the guide
    contract.

## TDD steps

1. **Installer** — RED: `tests/scripts/test_install_java_static_analysis.py`
   (stdlib-only AST check, java-absent → 1, repo-local / PATH /
   `PMD_INSTALL_DIR` short-circuits without download, pin uniqueness,
   `.pmd/` gitignore entry). GREEN: add the installer (verbatim from the
   issue spec) and the `.gitignore` entry.
2. **Default ruleset** — RED: XML-structure tests plus a pmd-gated fixture
   test (copied source under `target/` yields no findings). GREEN: ship
   `skills/static-analysis-integration/rulesets/pmd-quickstart.xml`.
3. **Registration docs** — RED: `tests/skills/test_static_analysis_java_lane.py`
   content guards for the lane row, Tier 1 entries, ruleset resolution, and
   the language-setup Java section; narrow #811's zero-lanes skeleton
   assertion to the still-unlanded lanes. GREEN: fill the two Java
   placeholders and add the Tier 1 entries.
4. **dev-setup** — RED: warn-only content guard. GREEN: the `pmd` block.
5. Gates: `bash scripts/ci-local.sh`; squash to clean conventional commits.

## Notes / resolved ambiguities

- The pin-uniqueness grep excludes `plugins/dev-team/CHANGELOG.md`: the
  release-please-generated changelog already contains the pinned PMD
  version string as a past plugin release version, which the issue's grep
  criterion did not anticipate. The intent — the PMD pin lives only in the
  installer — is asserted against every non-generated file.
- The default ruleset ships inside the static-analysis-integration skill
  (`rulesets/`, sibling of `adapters/`) so `/code-review` can reference it
  via `${CLAUDE_PLUGIN_ROOT}`.
- The SpotBugs follow-up issue (post-landing AC) is deferred to the epic
  owner — build sub-agents do not file tracker issues.
