# Changelog

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
