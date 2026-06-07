# Changelog

## [3.2.0](https://github.com/bdfinst/agentic-dev-team/compare/security-assessment-v3.1.1...security-assessment-v3.2.0) (2026-06-07)


### Features

* **security:** per-rule semgrep fixtures + measured fp_rate for the 36 custom rules ([#157](https://github.com/bdfinst/agentic-dev-team/issues/157)) ([e8bc52f](https://github.com/bdfinst/agentic-dev-team/commit/e8bc52faf4ca9b72543d341531844f05bcdc604e))


### Documentation

* remove implemented and issue-converted design docs ([#120](https://github.com/bdfinst/agentic-dev-team/issues/120)) ([11aa734](https://github.com/bdfinst/agentic-dev-team/commit/11aa734efc3fafab1a14e0839891397560f72ff2))

## [3.1.1](https://github.com/bdfinst/agentic-dev-team/compare/security-assessment-v3.1.0...security-assessment-v3.1.1) (2026-06-05)


### Miscellaneous

* convert pending specs/plans to GitHub issues; remove spec/plan files ([aea265e](https://github.com/bdfinst/agentic-dev-team/commit/aea265e5ad16c878a3cbd8f304917a51ea41cc10))
* convert pending specs/plans to GitHub issues; remove spec/plan files ([cf82c79](https://github.com/bdfinst/agentic-dev-team/commit/cf82c79fc7a5e590a04bd6bb479a72d7c87b7295))
* scrub stale helper-scripts plan reference in _lib.sh ([0d77bd2](https://github.com/bdfinst/agentic-dev-team/commit/0d77bd276911267488cc54aae9530dc5d73abad6))

## [3.1.0](https://github.com/bdfinst/agentic-dev-team/compare/security-assessment-v3.0.0...security-assessment-v3.1.0) (2026-06-04)


### Features

* **security-assessment:** add /upgrade command ([382b89f](https://github.com/bdfinst/agentic-dev-team/commit/382b89fff84ac5f770ffa1d0ce690708fe4f0baf))
* **security-assessment:** add /upgrade command ([3ebd5bb](https://github.com/bdfinst/agentic-dev-team/commit/3ebd5bb7f23088c956e6244d3b7146a48b25b44d))

## [3.0.0](https://github.com/bdfinst/agentic-dev-team/compare/security-assessment-v2.2.2...security-assessment-v3.0.0) (2026-06-02)


### ⚠ BREAKING CHANGES

* published plugin ids in the bfinster marketplace are now 'dev-team' and 'security-assessment' (previously 'agentic-dev-team' and 'agentic-security-assessment'). The 'agentic-' prefix carried no information — every plugin in this marketplace is agentic by definition.

### Code Refactoring

* **agents:** orchestration cluster has no remaining sweep work (12c) ([a7c3211](https://github.com/bdfinst/agentic-dev-team/commit/a7c321173bdc967dd56d53d4f867cef262c53726))
* rename plugins to dev-team and security-assessment ([a36bba2](https://github.com/bdfinst/agentic-dev-team/commit/a36bba28a670e5855605cadf794a7b092b04f2ba))
* **security-assessment:** sweep references; add install legacy-detection ([817e713](https://github.com/bdfinst/agentic-dev-team/commit/817e7132a9bb6b7946385ef84a9b12e56ee3848d))

## [2.2.2](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-assessment-v2.2.1...agentic-security-assessment-v2.2.2) (2026-06-02)


### Code Refactoring

* **agents:** orchestration cluster has no remaining sweep work (12c) ([a7c3211](https://github.com/bdfinst/agentic-dev-team/commit/a7c321173bdc967dd56d53d4f867cef262c53726))

## [2.2.1](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-assessment-v2.2.0...agentic-security-assessment-v2.2.1) (2026-05-12)


### Code Refactoring

* **security-assessment:** trim agents and apply progressive disclosure ([f8d3b21](https://github.com/bdfinst/agentic-dev-team/commit/f8d3b213aab3dca1de09b32d93d182b6feb49c9b))

## [2.2.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-assessment-v2.1.0...agentic-security-assessment-v2.2.0) (2026-05-01)


### Features

* **security-assessment:** add Stage 0 devil's advocate + confidence field to fp-reduction ([89b34e1](https://github.com/bdfinst/agentic-dev-team/commit/89b34e15b734ef7a2eabbdac7bb3c89790a0db9c))
* **security-assessment:** expand Phase 1b with 3 new judgment agents ([9dad5ee](https://github.com/bdfinst/agentic-dev-team/commit/9dad5ee6f1adabf7d376b12b02969f8cf291f2f8))
* **security-assessment:** Phase 1b expansion + fp-reduction Stage 0/confidence (v2.2.0) ([4e77037](https://github.com/bdfinst/agentic-dev-team/commit/4e7703795f383690fa974df54dac9cbed29bd1bb))
* **security-assessment:** recalibrate CRITICAL threshold against opus_repo_scan_test reference ([0c221cb](https://github.com/bdfinst/agentic-dev-team/commit/0c221cb037d779e345a6ede320682c0bb2eff957))
* **security-assessment:** recalibrate CRITICAL threshold against opus_repo_scan_test reference (v2.3.0) ([7a3c320](https://github.com/bdfinst/agentic-dev-team/commit/7a3c3201c73c2adcc2ba69bcd10003d6bc803718))


### Miscellaneous

* **security-assessment:** release 2.2.0 ([6296245](https://github.com/bdfinst/agentic-dev-team/commit/6296245eee29da567314fd627c928103a1bb823f))
* **security-assessment:** release 2.3.0 ([1d61422](https://github.com/bdfinst/agentic-dev-team/commit/1d614229f0b7d543bbfdccffb7067c181db49068))

## [2.3.0] (2026-05-01)


### Features

* **security-assessment:** recalibrate severity scoring against opus_repo_scan_test reference framework. CRITICAL is now reserved for findings exploitable immediately with no prerequisites that lead to data breach or fraud bypass (`score >= 9`). HIGH covers exploitable-with-moderate-effort issues (`score 6-8`). Earlier threshold of `score >= 7 → CRITICAL` combined with broad domain-class floors at 7 produced an inverted CRITICAL/HIGH pyramid (e.g. NextGen 198C/95H, Walletron 307C/10H). The recalibrated thresholds restore the proper distribution where HIGH > CRITICAL — validated against the reference's published 7C/12H/7M/3L example output.
* **security-assessment:** introduce discriminator-aware domain-class floors. `hardcoded-creds` floor=9 only when production-reachable; `dev-only-fallback` discriminator drops to 7 (HIGH). `unauth-admin-endpoint` floor=9 only when direct privilege escalation is enabled (model swap, token mint, cache flush, fraud bypass); `info-disclosure-only` discriminator drops to 7 (HIGH). New explicit floor=9 classes for `fail-open-scoring`, `emulation-bypass`, and `client-controlled-aggregate` matching reference S03-FS-01/02/03/04.


### Documentation

* **security-assessment:** `knowledge/severity-floors.json` adds `score_to_severity` thresholds and per-class `discriminator` fields. Each class rationale now cites the corresponding opus_repo_scan_test reference finding ID for audit traceability.
* **security-assessment:** `agents/fp-reduction.md` floor table updated with reference-finding citations and discriminator guidance.

## [2.2.0] (2026-05-01)


### Features

* **security-assessment:** add `recon-driven-scan` agent — bridges Phase 0 RECON narrative to concrete `file:line` evidence. Reads RECON's human-language risk descriptions and validates each described risk has matching code via targeted grep, finding patterns SAST cannot express (inverted-boolean TLS defaults, RCE shapes via expression libraries like Flee/Dynamic LINQ, header-driven SQL connection strings, body-trusted IDOR, masker exception PII fallback, format-preserving tokens). Includes a 28-pattern claim→search library covering unauth gRPC, TLS bypass, PII leak, crypto misuse, exception leak, SQL/code injection, SSRF, and DoS categories. Validated against the NextGen 2026-05-01 portfolio rerun: 12 repos previously scored zero-findings by SAST were re-scanned and produced 75 confirmed findings (8 CRITICAL, 17 HIGH) with zero false alarms. Notable additions the original SAST missed: 2 production SQL injections in `search-service`, RCE shape via Flee+Dynamic LINQ in `profile-custompipes`, inverted-boolean TLS bypass library-amplified across all consumer Lambdas in `notificationinfrastructure`, and expansion of the `Jupiter2020$` cross-repo credential reuse chain.
* **security-assessment:** Phase 1b is now a 5-agent parallel dispatch — `security-review` + `business-logic-domain-review` (via security-review-adapter) + `deep-code-reasoning` + `authorization-logic-review` + `recon-driven-scan` (latter three emit unified-finding-v1 directly, appended via `jq`).


### Documentation

* **security-assessment:** Phase 1b parallelization rule, artifacts table, and exec-report agent→phase mapping all updated. Plugin-level CLAUDE.md agent registry updated 11 → 12.

## [2.1.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-assessment-v2.0.0...agentic-security-assessment-v2.1.0) (2026-04-27)


### Features

* **security-assessment:** ship apply-accepted-risks.sh + primitives contract v1.3.0 ([caa62df](https://github.com/bdfinst/agentic-dev-team/commit/caa62dfa668f16736257d8fd004443da7800027e))
* **security-assessment:** ship apply-severity-floors.sh with externalized allow-list ([399f300](https://github.com/bdfinst/agentic-dev-team/commit/399f300a899187746038d81323f030d6688fd167))
* **security-assessment:** ship find-ci-files.sh for CI/CD definition discovery ([3782dac](https://github.com/bdfinst/agentic-dev-team/commit/3782dacd07a91e1465cf9833f67642d3450f74bb))
* **security-assessment:** ship phase-timer.sh with shell-test harness ([652e8a9](https://github.com/bdfinst/agentic-dev-team/commit/652e8a9cb8d56d79cf347e7646a72c4617a19c38))


### Code Refactoring

* **security-assessment:** address /code-review findings ([1f61c6e](https://github.com/bdfinst/agentic-dev-team/commit/1f61c6ea370a38b912b95fbb3b170ade45d67680))


### Miscellaneous

* **ci:** wire helper-script tests + shellcheck into CI ([8cb6126](https://github.com/bdfinst/agentic-dev-team/commit/8cb61268cea9da4b05ec7a059934bed22bbbefea))

## [2.0.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-assessment-v1.0.0...agentic-security-assessment-v2.0.0) (2026-04-24)


### ⚠ BREAKING CHANGES

* **security-assessment:** plugin renamed to eliminate prefix collision with the `security-review` agent that lives in `agentic-dev-team`. The agent name is contract-stable (per security-primitives-contract.md registry) and does not move. The plugin ships under its new name from 1.0.0 forward.

### Code Refactoring

* **security-assessment:** rename plugin agentic-security-review → agentic-security-assessment (1.0.0) ([9195f22](https://github.com/bdfinst/agentic-dev-team/commit/9195f22a29b181ff049c9b7e689bfa2b69fa3c2a))


### Documentation

* **agentic-dev-team:** update cross-references to renamed companion plugin + history note on rename docs ([87a7a34](https://github.com/bdfinst/agentic-dev-team/commit/87a7a3445a26e2471ceff312fe34ecd92a3098de))
* **security-assessment:** update plugin-internal references to new name + CHANGELOG 1.0.0 migration entry ([7e0ebc7](https://github.com/bdfinst/agentic-dev-team/commit/7e0ebc7e4adc4a0a10b7f4b96bc00c0e8f4e355b))

## 1.0.0 — RENAMED from `agentic-security-review` (2026-04-24)

### BREAKING CHANGE — plugin rename

The plugin has been renamed from `agentic-security-review` to `agentic-security-assessment` to eliminate the prefix collision with the `security-review` agent that lives in `agentic-dev-team`. The agent name is contract-stable and did not move.

### Migration

Existing users must update the following references:

1. `claude plugin install`: `agentic-security-review@bfinster` → `agentic-security-assessment@bfinster`
2. `.claude/settings.local.json` opt-out snippets referencing `plugins/agentic-security-review/` → `plugins/agentic-security-assessment/`
3. Any automation, docs, or commit-scope conventions citing the plugin path or name

The plugin's primitives-contract compatibility is unchanged (`^1.0.0`). The `security-review` agent ID in the contract registry is unchanged. No runtime behavior change.

Link to spec: `docs/specs/plugin-rename-security-assessment.md`.

## [0.3.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-review-v0.2.1...agentic-security-review-v0.3.0) (2026-04-22)


### Features

* **security-review:** add NATS/messaging semgrep rules and training data inference detection (gaps 1, 6) ([fdf87c5](https://github.com/bdfinst/agentic-dev-team/commit/fdf87c57e2dcbcc41780e25a0bd4b89cca59ecee))
* **security-review:** add serialization rules, base64 scan tool, datastore/Cassandra rules (gaps 2, 4, 5) ([48efd6e](https://github.com/bdfinst/agentic-dev-team/commit/48efd6e8bfe3b69cf9404e812ef600fb607695f0))
* **security-review:** add severity consistency check, cross-cutting section, report verifier (gaps 3, 7, 8) ([4b270de](https://github.com/bdfinst/agentic-dev-team/commit/4b270ded5250b2b6d5e35e052f769472c362e50e))
* **security-review:** add Windows PowerShell install script ([37930f5](https://github.com/bdfinst/agentic-dev-team/commit/37930f522ee3199937f9be2f5b018357fd9625b5))


### Bug Fixes

* **security-review:** upgrade all agents to opus ([5868b30](https://github.com/bdfinst/agentic-dev-team/commit/5868b30d971b354a2690482445e5ea04921f69a1))

## [0.2.1](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-review-v0.2.0...agentic-security-review-v0.2.1) (2026-04-22)


### Bug Fixes

* **security-review:** pin CWE display format to match opus_repo_scan_test reference ([74eafe2](https://github.com/bdfinst/agentic-dev-team/commit/74eafe262c4440d885603e556c9d6e2e464fedbc))

## [0.2.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-security-review-v0.1.0...agentic-security-review-v0.2.0) (2026-04-22)


### Features

* **fp-reduction:** add domain-class severity floors to exploitability scoring ([e7addcf](https://github.com/bdfinst/agentic-dev-team/commit/e7addcf492ac7664440dde35cd2262b2072e2ca7))
* **hooks:** auto-time every Agent dispatch via PreToolUse+PostToolUse hook ([f4fa9ce](https://github.com/bdfinst/agentic-dev-team/commit/f4fa9ce1eb2d8bfc8546840adef426173600e12b))
* per-plugin release-please + registry finalization (Step 20) ([5350137](https://github.com/bdfinst/agentic-dev-team/commit/53501373ab8adb3c8055416368cc336264c9d215))
* **pipeline:** multi-target parallelism, Phase-4-reorder, mandatory timing ([5f49180](https://github.com/bdfinst/agentic-dev-team/commit/5f491807bec41a943c079f852a0e263488260ebc))
* **plugin:** add install-macos.sh to install tools the plugin calls ([e149423](https://github.com/bdfinst/agentic-dev-team/commit/e149423c0d5cb520f9c2b3d852e0b251e89e4530))
* **scripts:** extract Phase 1c / 2b / CI-scope fixes to deterministic scripts ([d620475](https://github.com/bdfinst/agentic-dev-team/commit/d620475a404875fdbf748fb8e572cda13f0350dd))
* **security-review:** Phase B detection agents + skills (Steps 8, 9, 10, 11) ([cac5a43](https://github.com/bdfinst/agentic-dev-team/commit/cac5a43434d2b7ed87006a38b4a7e273510f3c4b))
* **security-review:** Phase B orchestration (Steps 12, 13, 14) ([2821822](https://github.com/bdfinst/agentic-dev-team/commit/2821822b12f1e03c5d31413eeb7fdc030f5f3512))
* **security-review:** PostToolUse auto-scan hook + 4 custom semgrep rulesets ([1be4137](https://github.com/bdfinst/agentic-dev-team/commit/1be413755fb034b33c89e10a2457dac98ae9e61d))
* **security-review:** red-team analyzers + /export-pdf (Steps 18 + 19) ([b0605aa](https://github.com/bdfinst/agentic-dev-team/commit/b0605aadfb68764a39a038b9857f0ad61426086a))
* **security-review:** red-team harness scaffold + libs + scope enforcement (Step 15) ([2385398](https://github.com/bdfinst/agentic-dev-team/commit/2385398fcf9fe08815393ea6c36689b06ee729b6))
* **security-review:** red-team probes 01-08 (Steps 16 + 17) ([1c3d693](https://github.com/bdfinst/agentic-dev-team/commit/1c3d69334ee356a344043d9a786b7ce196c59500))
* **security-review:** scaffold companion plugin ([8324dc2](https://github.com/bdfinst/agentic-dev-team/commit/8324dc2545d01960abaaa63cb841b29fd4e8edfa))


### Bug Fixes

* **fp-reduction:** enforce schema-conformant nested disposition register shape ([b4be5ff](https://github.com/bdfinst/agentic-dev-team/commit/b4be5ff132a9af6cbc40c5d885f92c0bbbf74190))
* **scope:** CI/CD workflow files explicitly in scope for static + security review ([763924f](https://github.com/bdfinst/agentic-dev-team/commit/763924fc7ad55f53b3ca96a19801f57e5badb390))
* **security-assessment:** make ACCEPTED-RISKS suppression an enforced Phase 1c gate ([71de667](https://github.com/bdfinst/agentic-dev-team/commit/71de66721120b8f479a829b2a89165618c5f9efb))


### Documentation

* move per-plugin install instructions into each plugin's README ([26bca28](https://github.com/bdfinst/agentic-dev-team/commit/26bca280debae8d430bea0389a70caf8d1221400))


### Miscellaneous

* **security-review:** gitignore pycache + harness runtime dirs ([8f03a46](https://github.com/bdfinst/agentic-dev-team/commit/8f03a464d2a69ca143b564b7931c69d9ebe94e24))
