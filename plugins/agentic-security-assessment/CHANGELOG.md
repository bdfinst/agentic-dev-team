# Changelog

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
