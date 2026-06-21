# Changelog

## [7.0.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.11.1...dev-team-v7.0.0) (2026-06-21)


### ⚠ BREAKING CHANGES

* **routing:** agent frontmatter uses effort: bands, not model: tiers. The resolver accepts legacy model: tiers for one deprecation release.

### Features

* **dev-team:** release ownership-engineering improvements; add commitlint guard ([#339](https://github.com/bdfinst/agentic-dev-team/issues/339)) ([a689677](https://github.com/bdfinst/agentic-dev-team/commit/a68967749d6222b72f9372047628194b8cf5b3dd))
* **routing:** effort-band model routing (replaces model: tiers) ([#337](https://github.com/bdfinst/agentic-dev-team/issues/337)) ([2fda3c1](https://github.com/bdfinst/agentic-dev-team/commit/2fda3c1ef292410b0bb060a09892564eedd3fb32))

## [6.11.1](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.11.0...dev-team-v6.11.1) (2026-06-20)


### Code Refactoring

* **test-review:** consolidate overlaps, rename Farley scorer, dedupe shared prose ([#324](https://github.com/bdfinst/agentic-dev-team/issues/324)) ([dd2d1da](https://github.com/bdfinst/agentic-dev-team/commit/dd2d1daf317272b2c11b6488c32c865147d0c038))


### Documentation

* **skills:** disambiguate /agent-readiness from /harness-audit ([#325](https://github.com/bdfinst/agentic-dev-team/issues/325)) ([f647247](https://github.com/bdfinst/agentic-dev-team/commit/f6472472bdc24c4bc9aeec12ff19fc20c3732ebc))

## [6.11.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.10.1...dev-team-v6.11.0) (2026-06-19)


### Features

* **eval:** confidence-pyramid improvements (registry, dispatch, cache, citation lint, integration tier) ([#315](https://github.com/bdfinst/agentic-dev-team/issues/315)) ([b560880](https://github.com/bdfinst/agentic-dev-team/commit/b56088082f4952bd51178bb1d66843e61788b8ed))
* **evals:** backfill cites: frontmatter on reviewer agents ([#319](https://github.com/bdfinst/agentic-dev-team/issues/319)) ([e37c627](https://github.com/bdfinst/agentic-dev-team/commit/e37c62774990207981565ad111fe04d3ca905e29))
* **evals:** wire cache + integration tier + cites enforcement into /agent-eval and /agent-create ([#322](https://github.com/bdfinst/agentic-dev-team/issues/322)) ([a3c623c](https://github.com/bdfinst/agentic-dev-team/commit/a3c623c84616fa84d46d85fa34f9a2873458fd8a))
* **test-modernize:** make Phase-3 disabled-test resolution a Phase-4 contract ([#318](https://github.com/bdfinst/agentic-dev-team/issues/318)) ([e30ecba](https://github.com/bdfinst/agentic-dev-team/commit/e30ecba9824776be4b9a2b371d90e7dc8e5ad032))
* **test-modernize:** per-Story mutation testing in Phase 4 + end-of-phase test review loop (MVP probe) ([#316](https://github.com/bdfinst/agentic-dev-team/issues/316)) ([df30551](https://github.com/bdfinst/agentic-dev-team/commit/df3055178e0a137a173ec8ff099d59159f8cbc73))

## [6.10.1](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.10.0...dev-team-v6.10.1) (2026-06-19)


### Documentation

* add /ship + /test-modernize workflow doc; alphabetize skill/agent tables ([#277](https://github.com/bdfinst/agentic-dev-team/issues/277)) ([4eb563d](https://github.com/bdfinst/agentic-dev-team/commit/4eb563d56d9aff832860af35295302c2ba7d4b0c))


### Miscellaneous

* **plugins:** remove deprecated legacy stubs and rename-migration upgrade path ([#275](https://github.com/bdfinst/agentic-dev-team/issues/275)) ([2048687](https://github.com/bdfinst/agentic-dev-team/commit/2048687a1f2b3dad14de9b8538191a8f4fdd6893))

## [6.10.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.9.0...dev-team-v6.10.0) (2026-06-18)


### Features

* **test-modernize:** bind component tests to approved Gherkin scenarios ([#273](https://github.com/bdfinst/agentic-dev-team/issues/273)) ([aa6bef7](https://github.com/bdfinst/agentic-dev-team/commit/aa6bef722da8d518c7ccfbf1e17ef08b7a38b087))

## [6.9.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.8.0...dev-team-v6.9.0) (2026-06-18)


### Features

* **skills:** /test-modernize orchestrator workflow ([#271](https://github.com/bdfinst/agentic-dev-team/issues/271)) ([3c81e0f](https://github.com/bdfinst/agentic-dev-team/commit/3c81e0f0214b87dad2d75c0cb24efd6ea6e8b221))

## [6.8.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.7.0...dev-team-v6.8.0) (2026-06-18)


### Features

* **agents:** add identity personas to all 11 team agents ([#253](https://github.com/bdfinst/agentic-dev-team/issues/253)) ([cd751d9](https://github.com/bdfinst/agentic-dev-team/commit/cd751d921c1ecc515f71eee222047058d15027ec))
* **build:** JS project bootstrap gate — invoke js-project-init when package.json missing ([#257](https://github.com/bdfinst/agentic-dev-team/issues/257)) ([4b6ff4e](https://github.com/bdfinst/agentic-dev-team/commit/4b6ff4ee1ca3450639346089952015f264703442))
* **js-project-init:** add lint-staged with pre-commit auto-fix ([#256](https://github.com/bdfinst/agentic-dev-team/issues/256)) ([d6d3c64](https://github.com/bdfinst/agentic-dev-team/commit/d6d3c6412005b1235f2b369e979c01869712a53b))
* **qa-engineer,test-design:** rewrite qa-engineer as Senior SDET; lock test-design vocabulary to MinimumCD ([#270](https://github.com/bdfinst/agentic-dev-team/issues/270)) ([f189ebf](https://github.com/bdfinst/agentic-dev-team/commit/f189ebf29a509e67ab6fe7198a0655897088e187))
* **version:** make /version a mechanical, deterministic lookup ([#259](https://github.com/bdfinst/agentic-dev-team/issues/259)) ([a553754](https://github.com/bdfinst/agentic-dev-team/commit/a553754be97325cdfd7c08aea97e2f7c0a17dcd1))


### Bug Fixes

* **build:** ship the parallel-build wave scripts inside the plugin ([#261](https://github.com/bdfinst/agentic-dev-team/issues/261)) ([77d9e39](https://github.com/bdfinst/agentic-dev-team/commit/77d9e39761ea115a3c475dc99142c02c2f51c5ab))
* **security-assessment:** stop shipping build/test scripts; make runtime scripts discoverable ([#263](https://github.com/bdfinst/agentic-dev-team/issues/263)) ([5ae7afc](https://github.com/bdfinst/agentic-dev-team/commit/5ae7afc4a90d60e6a231bec462a17dc77dd31a1d))
* **upgrade:** skip legacy-id migration when version &gt;= 6.1.0 ([#249](https://github.com/bdfinst/agentic-dev-team/issues/249)) ([770c413](https://github.com/bdfinst/agentic-dev-team/commit/770c41354680275784e4a04890db8e6564972138))


### Performance Improvements

* **ci:** parallelize local pre-push gates and bats suites ([#247](https://github.com/bdfinst/agentic-dev-team/issues/247)) ([836be51](https://github.com/bdfinst/agentic-dev-team/commit/836be51bb8b026b9e2afe4f9af4c17c7834fe552))


### Documentation

* fix duplicate examples in GETTING-STARTED.md skill invocation section ([#269](https://github.com/bdfinst/agentic-dev-team/issues/269)) ([0cc0c6a](https://github.com/bdfinst/agentic-dev-team/commit/0cc0c6a684f0baa7c47910978284c9d6da730989))

## [6.7.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.6.1...dev-team-v6.7.0) (2026-06-08)


### Features

* **build:** wave-aware concurrent build ([#224](https://github.com/bdfinst/agentic-dev-team/issues/224)) ([#242](https://github.com/bdfinst/agentic-dev-team/issues/242)) ([9137017](https://github.com/bdfinst/agentic-dev-team/commit/913701728da691cb0be09cbd5aeb022946b4fabd))
* **issues-from-plan:** spec parent + DAG-linked slice children ([#225](https://github.com/bdfinst/agentic-dev-team/issues/225)) ([#243](https://github.com/bdfinst/agentic-dev-team/issues/243)) ([3306499](https://github.com/bdfinst/agentic-dev-team/commit/330649946f10852d19099fe991c1d5c4f4885f82))
* **plan:** GitHub-origin post-plan issue gate ([#226](https://github.com/bdfinst/agentic-dev-team/issues/226)) ([#244](https://github.com/bdfinst/agentic-dev-team/issues/244)) ([8d10fde](https://github.com/bdfinst/agentic-dev-team/commit/8d10fdef1318d4b4a61a7ff7a239427763b610f7))
* **plan:** parallelization-review persona ([#223](https://github.com/bdfinst/agentic-dev-team/issues/223)) ([#241](https://github.com/bdfinst/agentic-dev-team/issues/241)) ([3a4a173](https://github.com/bdfinst/agentic-dev-team/commit/3a4a17397a62414993c443fbb6594092377ab694))
* **plan:** slice dependency metadata + wave computation ([#222](https://github.com/bdfinst/agentic-dev-team/issues/222)) ([#240](https://github.com/bdfinst/agentic-dev-team/issues/240)) ([e8c9aa9](https://github.com/bdfinst/agentic-dev-team/commit/e8c9aa9123c403b3e125f79d960091a02d90ca0d))
* **security-scan:** offline-harden gitleaks + trivy ([#53](https://github.com/bdfinst/agentic-dev-team/issues/53)) ([#245](https://github.com/bdfinst/agentic-dev-team/issues/245)) ([0dd89ef](https://github.com/bdfinst/agentic-dev-team/commit/0dd89ef59d1f1726cbae66b7278b097dca2c58ed))
* **session-review:** wire raw-log semantic tier + methodology lens ([#214](https://github.com/bdfinst/agentic-dev-team/issues/214)) ([#239](https://github.com/bdfinst/agentic-dev-team/issues/239)) ([a1dd258](https://github.com/bdfinst/agentic-dev-team/commit/a1dd2582b8e60f63df3cbd16446d181775a4a3a9))


### Miscellaneous

* remove issue-tracked specs, spikes, and plans ([#215](https://github.com/bdfinst/agentic-dev-team/issues/215)) ([#216](https://github.com/bdfinst/agentic-dev-team/issues/216)) ([d058860](https://github.com/bdfinst/agentic-dev-team/commit/d05886080c458ec579b58f1f63ea3bf7524f3433))

## [6.6.1](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.6.0...dev-team-v6.6.1) (2026-06-07)


### Bug Fixes

* **release:** sync marketplace catalog via release-please extra-files ([#210](https://github.com/bdfinst/agentic-dev-team/issues/210)) ([c84611a](https://github.com/bdfinst/agentic-dev-team/commit/c84611ad559d3a86d884836337a9b7c3eb007772))

## [6.6.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.5.0...dev-team-v6.6.0) (2026-06-07)


### Features

* **agent-eval:** eval variance aggregator — pass@k, flap, quarantine ([#103](https://github.com/bdfinst/agentic-dev-team/issues/103)) ([#196](https://github.com/bdfinst/agentic-dev-team/issues/196)) ([4a2abcb](https://github.com/bdfinst/agentic-dev-team/commit/4a2abcb8fd1caf98865776e355d146b2af3e585f))
* **evals:** incremental per-agent eval runs (not all-or-nothing) ([#206](https://github.com/bdfinst/agentic-dev-team/issues/206)) ([8d7d9e0](https://github.com/bdfinst/agentic-dev-team/commit/8d7d9e03b3ab50b734d210b71bc34c9fead9e9ab))
* **evals:** make the resumable sweep the default mode of run-full-eval.sh ([#208](https://github.com/bdfinst/agentic-dev-team/issues/208)) ([bba7734](https://github.com/bdfinst/agentic-dev-team/commit/bba7734a27667c39def7cc12edee49162fba592d))
* **evals:** resumable --sweep mode for run-full-eval.sh ([#207](https://github.com/bdfinst/agentic-dev-team/issues/207)) ([088adce](https://github.com/bdfinst/agentic-dev-team/commit/088adcef48225de5718c458f7157b0a6489aae59))
* **evals:** run-full-eval.sh — full corpus run + baseline refresh + auto-merge PR ([#202](https://github.com/bdfinst/agentic-dev-team/issues/202)) ([37e0280](https://github.com/bdfinst/agentic-dev-team/commit/37e028051096723f47112199bd3229d0fec52576))
* **session-review:** cross-machine union read ([#178](https://github.com/bdfinst/agentic-dev-team/issues/178)) + utilization fix ([#182](https://github.com/bdfinst/agentic-dev-team/issues/182)) ([#188](https://github.com/bdfinst/agentic-dev-team/issues/188)) ([d6280b6](https://github.com/bdfinst/agentic-dev-team/commit/d6280b6019f3e54ac161e29b1612b36d12e66d50))
* **session-review:** frequency→lever escalation (Delta C, [#179](https://github.com/bdfinst/agentic-dev-team/issues/179)) ([#189](https://github.com/bdfinst/agentic-dev-team/issues/189)) ([3328c81](https://github.com/bdfinst/agentic-dev-team/commit/3328c81333338179c5b9713a7c780026fea74443))
* **session-review:** per-session gate instrumentation + bypass↔rework correlation ([#111](https://github.com/bdfinst/agentic-dev-team/issues/111)) ([#200](https://github.com/bdfinst/agentic-dev-team/issues/200)) ([384138b](https://github.com/bdfinst/agentic-dev-team/commit/384138b0a6954a9f1516579e4829cf5dce9d616b))
* **session-review:** telemetry sync transport + config validation + security docs ([#187](https://github.com/bdfinst/agentic-dev-team/issues/187)) ([559cf3d](https://github.com/bdfinst/agentic-dev-team/commit/559cf3d04561f83e68be918928dd47f4fdc412a9))
* **telemetry:** wire CI cost-regression gate to real cross-machine baseline ([#171](https://github.com/bdfinst/agentic-dev-team/issues/171)) ([#192](https://github.com/bdfinst/agentic-dev-team/issues/192)) ([531a794](https://github.com/bdfinst/agentic-dev-team/commit/531a794f3e9b26e8c7fcc9ea1c28a606e7293784))


### Bug Fixes

* **cost-meter:** attribute by model + thread; drop inert buckets ([#170](https://github.com/bdfinst/agentic-dev-team/issues/170)) ([#183](https://github.com/bdfinst/agentic-dev-team/issues/183)) ([c7a2b2a](https://github.com/bdfinst/agentic-dev-team/commit/c7a2b2aaf572f7586f8cff884f76942ce2810280))
* **mutation-gate:** _timeout fallback must not write to stdout ([#197](https://github.com/bdfinst/agentic-dev-team/issues/197)) ([12b1936](https://github.com/bdfinst/agentic-dev-team/commit/12b19360ae2e38a92a49cac9f2a3255c768081da))
* **review-gate:** bind .review-passed to staged CONTENT, not paths ([#193](https://github.com/bdfinst/agentic-dev-team/issues/193)) ([#195](https://github.com/bdfinst/agentic-dev-team/issues/195)) ([5733af3](https://github.com/bdfinst/agentic-dev-team/commit/5733af379e38add39e74bbad341eb57802dc5452))
* **skills:** reference prompt templates by explicit plugin-root path ([#181](https://github.com/bdfinst/agentic-dev-team/issues/181)) ([a2be7cb](https://github.com/bdfinst/agentic-dev-team/commit/a2be7cbe7c17f7a239ebcb41ef3bec931a5e93c2)), closes [#173](https://github.com/bdfinst/agentic-dev-team/issues/173)


### Documentation

* adopt North Star + scope the self-improvement loop to /session-review deltas ([#172](https://github.com/bdfinst/agentic-dev-team/issues/172)) ([6003609](https://github.com/bdfinst/agentic-dev-team/commit/600360961a6acb97a4f86abbcd86949872a6b8d8))
* **concurrent-use:** resolve [#109](https://github.com/bdfinst/agentic-dev-team/issues/109) Phase 2 — one worktree per agent ([#194](https://github.com/bdfinst/agentic-dev-team/issues/194)) ([3751b06](https://github.com/bdfinst/agentic-dev-team/commit/3751b069e281119cba4b6b88f4a52ccc075ee764))
* eval running guide, maintenance guide, and feature-verification plan ([#201](https://github.com/bdfinst/agentic-dev-team/issues/201)) ([847fd02](https://github.com/bdfinst/agentic-dev-team/commit/847fd02adf5e503704e58ff6b1c02917c2cd37f5))
* how to give CI read-only access to the telemetry repo ([#171](https://github.com/bdfinst/agentic-dev-team/issues/171) prep) ([#191](https://github.com/bdfinst/agentic-dev-team/issues/191)) ([9fddacd](https://github.com/bdfinst/agentic-dev-team/commit/9fddacdc315440a3c326b18f6c21c56d19feb190))


### Miscellaneous

* Wave 1 hygiene — scope honesty + orphan spec + beacon scope ([#185](https://github.com/bdfinst/agentic-dev-team/issues/185)) ([86be934](https://github.com/bdfinst/agentic-dev-team/commit/86be934db259d213d26cdab4c8a5c4e386275e47)), closes [#105](https://github.com/bdfinst/agentic-dev-team/issues/105) [#115](https://github.com/bdfinst/agentic-dev-team/issues/115) [#106](https://github.com/bdfinst/agentic-dev-team/issues/106)

## [6.5.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.4.0...dev-team-v6.5.0) (2026-06-07)


### Features

* **cost-meter:** account-level pace/quota guidance ([#151](https://github.com/bdfinst/agentic-dev-team/issues/151)) ([4ea4dd1](https://github.com/bdfinst/agentic-dev-team/commit/4ea4dd1dc93574f7f0fa09f7138bbfa2c1f76134))
* **cost-meter:** attribute spend per command and per fix-loop iteration ([#147](https://github.com/bdfinst/agentic-dev-team/issues/147)) ([05203d5](https://github.com/bdfinst/agentic-dev-team/commit/05203d51c0c97f19b8a4a04dba460eb18fc8ec37))
* **cost-meter:** attribute spend per orchestration phase ([#148](https://github.com/bdfinst/agentic-dev-team/issues/148)) ([522b428](https://github.com/bdfinst/agentic-dev-team/commit/522b42806de6c61c81bea3713a15381ed16a3dcb))
* **session-review:** /session-review skill + session-analysis agent ([#154](https://github.com/bdfinst/agentic-dev-team/issues/154)) ([bccf6df](https://github.com/bdfinst/agentic-dev-team/commit/bccf6dfee54fd3ff1b1718ac5efa7bca4b796d7a))
* **session-review:** persist trend digest + harness-audit consumption ([#155](https://github.com/bdfinst/agentic-dev-team/issues/155)) ([833c606](https://github.com/bdfinst/agentic-dev-team/commit/833c6060a2ecb8890a7d1e4890ac1cd7bbc1299d))
* **telemetry:** capture agent-/auto-invoked skills distinctly; tighten bypass detection ([#145](https://github.com/bdfinst/agentic-dev-team/issues/145)) ([2d025f1](https://github.com/bdfinst/agentic-dev-team/commit/2d025f1b4a59b634492204d6c7a93d98c932155a))


### Bug Fixes

* extend prose-honesty gate to sibling docs and clean un-instrumented targets ([#137](https://github.com/bdfinst/agentic-dev-team/issues/137)) ([e537495](https://github.com/bdfinst/agentic-dev-team/commit/e537495ec6389124042163c80011a4a3f9ce2c62))
* **pr:** make /pr own the human gate for code review ([#160](https://github.com/bdfinst/agentic-dev-team/issues/160)) ([e26175a](https://github.com/bdfinst/agentic-dev-team/commit/e26175a43542e592a11d85838b10f50f68257dfc))
* **pr:** make /pr own the human gate for code review ([#165](https://github.com/bdfinst/agentic-dev-team/issues/165)) ([26741d5](https://github.com/bdfinst/agentic-dev-team/commit/26741d58cf909b2c21b4f1a10e14bca7bc6f3d49))


### Documentation

* remove implemented and issue-converted design docs ([#120](https://github.com/bdfinst/agentic-dev-team/issues/120)) ([11aa734](https://github.com/bdfinst/agentic-dev-team/commit/11aa734efc3fafab1a14e0839891397560f72ff2))
* **session-review:** document OSS complements (ccusage, OpenTelemetry, claude-code-log) ([#156](https://github.com/bdfinst/agentic-dev-team/issues/156)) ([71e3ed5](https://github.com/bdfinst/agentic-dev-team/commit/71e3ed5efabce0f9dd9906113b38010931364998))
* **session-review:** umbrella overview tying the harness together ([#158](https://github.com/bdfinst/agentic-dev-team/issues/158)) ([ad3a21d](https://github.com/bdfinst/agentic-dev-team/commit/ad3a21d3251c8eddc11fd18c89af9fdb97aaf727))

## [6.4.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.3.0...dev-team-v6.4.0) (2026-06-06)


### Features

* **dev-team:** add no-colon description rule to agent-audit, spec for commands→skills migration ([c2a6a0d](https://github.com/bdfinst/agentic-dev-team/commit/c2a6a0db2926fe410db5f63e8fdcece4a75de08b))
* **dev-team:** collapse commands/ into skills/ — unified capability layer ([f9fde67](https://github.com/bdfinst/agentic-dev-team/commit/f9fde673a880859d9f4f74c00cd22a08536c4b57))


### Bug Fixes

* **dev-team:** update bats test paths and regenerate knowledge index after commands→skills migration ([ca976e7](https://github.com/bdfinst/agentic-dev-team/commit/ca976e75a8cb12ddbc0cbcec14260c8caaa8fda5))

## [6.3.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.2.0...dev-team-v6.3.0) (2026-06-05)


### Features

* **dev-team:** /explore command, file-based /triage, agent-create reconcile ([#56](https://github.com/bdfinst/agentic-dev-team/issues/56) [#57](https://github.com/bdfinst/agentic-dev-team/issues/57) [#58](https://github.com/bdfinst/agentic-dev-team/issues/58)) ([#94](https://github.com/bdfinst/agentic-dev-team/issues/94)) ([fb790d6](https://github.com/bdfinst/agentic-dev-team/commit/fb790d6521f75978e287dda11270b879aff3c6e7))
* **dev-team:** automate test-layer-gates fixture as an agent-eval ([#85](https://github.com/bdfinst/agentic-dev-team/issues/85)) ([#91](https://github.com/bdfinst/agentic-dev-team/issues/91)) ([84cfd35](https://github.com/bdfinst/agentic-dev-team/commit/84cfd355c77f1606e58fab5209583afffbff2f52))
* **dev-team:** xUnit testing knowledge build-out ([#73](https://github.com/bdfinst/agentic-dev-team/issues/73) [#74](https://github.com/bdfinst/agentic-dev-team/issues/74) [#75](https://github.com/bdfinst/agentic-dev-team/issues/75) [#76](https://github.com/bdfinst/agentic-dev-team/issues/76)) ([#93](https://github.com/bdfinst/agentic-dev-team/issues/93)) ([60ca0ae](https://github.com/bdfinst/agentic-dev-team/commit/60ca0ae4a9fa5413f23a324ff279904ffb2bc04d))

## [6.2.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.1.0...dev-team-v6.2.0) (2026-06-05)


### Features

* **dev-team:** add test-layer-gates knowledge file + fixture ([#80](https://github.com/bdfinst/agentic-dev-team/issues/80)) ([884415d](https://github.com/bdfinst/agentic-dev-team/commit/884415d5e6add81334487d35874b355d6ac0e7da))
* **dev-team:** add test-strategy knowledge file (xUnit Test Strategy patterns) ([0e7f58a](https://github.com/bdfinst/agentic-dev-team/commit/0e7f58a1515d77daf674fe8ae554aa26b3013e3f))
* **dev-team:** add test-strategy knowledge file (xUnit Test Strategy patterns) ([c101225](https://github.com/bdfinst/agentic-dev-team/commit/c101225c513374fa5d1ebff95887076f89195830))
* **dev-team:** behavior pre-gates + redundancy check for test-design-advisor ([#80](https://github.com/bdfinst/agentic-dev-team/issues/80)) ([20b8053](https://github.com/bdfinst/agentic-dev-team/commit/20b80537ec8613a53d070c50673c97e400e40f55))
* **dev-team:** complete testing-strategy epic ([#81](https://github.com/bdfinst/agentic-dev-team/issues/81) [#82](https://github.com/bdfinst/agentic-dev-team/issues/82) [#83](https://github.com/bdfinst/agentic-dev-team/issues/83) [#84](https://github.com/bdfinst/agentic-dev-team/issues/84)) ([#90](https://github.com/bdfinst/agentic-dev-team/issues/90)) ([19abe6c](https://github.com/bdfinst/agentic-dev-team/commit/19abe6c1ee20cf5662f7022ec9db2da8ac717e86))
* **dev-team:** register test-layer-gates + verify gate firings vs fixture ([#80](https://github.com/bdfinst/agentic-dev-team/issues/80)) ([8d847cb](https://github.com/bdfinst/agentic-dev-team/commit/8d847cbac0a906bb55bb620765aeeeee0cf8a83f))
* **dev-team:** skip /code-review for documentation-only changesets ([f3aac6f](https://github.com/bdfinst/agentic-dev-team/commit/f3aac6fff08f06423666c281e0dbd9df25b5f198))
* **dev-team:** skip /code-review for documentation-only changesets ([2b75996](https://github.com/bdfinst/agentic-dev-team/commit/2b75996abdf2779753dfdfe8b47efe187328bc38))
* **dev-team:** wire behavior pre-gates + redundancy into test-design-advisor ([#80](https://github.com/bdfinst/agentic-dev-team/issues/80)) ([f67b5a3](https://github.com/bdfinst/agentic-dev-team/commit/f67b5a3b0513dbee015170ca9a58ef8541836a3e))


### Bug Fixes

* **dev-team:** repoint rule-id adapter contract refs + fix skill-wiring test ([f7b0cb6](https://github.com/bdfinst/agentic-dev-team/commit/f7b0cb69eb9e483f6d1496144c2c4e04ae128f6a))
* **dev-team:** repoint rule-id adapter contract refs + fix skill-wiring test ([9f685a3](https://github.com/bdfinst/agentic-dev-team/commit/9f685a303c867407202f20ed8ebc22d72f47a328)), closes [#65](https://github.com/bdfinst/agentic-dev-team/issues/65)
* **dev-team:** sync /review alias frontmatter with /code-review ([#88](https://github.com/bdfinst/agentic-dev-team/issues/88)) ([5ffd156](https://github.com/bdfinst/agentic-dev-team/commit/5ffd15657bd78e36e0788605d97944194f0af964))
* **dev-team:** sync /review alias frontmatter with /code-review ([#88](https://github.com/bdfinst/agentic-dev-team/issues/88)) ([ae0ee28](https://github.com/bdfinst/agentic-dev-team/commit/ae0ee281d1e2a8110c4bbeed2f77ab1dc38564cc))


### Documentation

* **dev-team:** document doc-only short-circuit in code-review-process ([f59f008](https://github.com/bdfinst/agentic-dev-team/commit/f59f0084b060c117ddddd4b4037d25ecf4a8d442))


### Miscellaneous

* convert pending specs/plans to GitHub issues; remove spec/plan files ([aea265e](https://github.com/bdfinst/agentic-dev-team/commit/aea265e5ad16c878a3cbd8f304917a51ea41cc10))
* convert pending specs/plans to GitHub issues; remove spec/plan files ([cf82c79](https://github.com/bdfinst/agentic-dev-team/commit/cf82c79fc7a5e590a04bd6bb479a72d7c87b7295))
* **dev-team:** resolve agent-audit compliance gaps ([16b4aa9](https://github.com/bdfinst/agentic-dev-team/commit/16b4aa9b86b7d0f72997a3973c196a3e61c8ba31))
* **dev-team:** resolve agent-audit compliance gaps ([ca89416](https://github.com/bdfinst/agentic-dev-team/commit/ca89416fbde2c79d3d72f28e4d51b66a0f4851bc))

## [6.1.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v6.0.0...dev-team-v6.1.0) (2026-06-04)


### Features

* **dev-team:** add test-design and CD test-architecture capabilities ([5281b37](https://github.com/bdfinst/agentic-dev-team/commit/5281b37e9ae693906d81d00db7c68715d836a411))
* **dev-team:** handle out-of-repo tests + document test evaluation workflow ([42277cf](https://github.com/bdfinst/agentic-dev-team/commit/42277cfb43ad7d18bfe15d835c58a72d9993e101))
* **dev-team:** outside-in baseline before refactor in test evaluation ([7624645](https://github.com/bdfinst/agentic-dev-team/commit/76246450dca152fceb755074fd7fa1e62dcc5ede))
* **dev-team:** test design + CD test architecture capabilities ([4177444](https://github.com/bdfinst/agentic-dev-team/commit/41774446a23d7d2a9099012bf897d9d687bbd47d))

## [6.0.0](https://github.com/bdfinst/agentic-dev-team/compare/dev-team-v5.6.0...dev-team-v6.0.0) (2026-06-02)


### ⚠ BREAKING CHANGES

* published plugin ids in the bfinster marketplace are now 'dev-team' and 'security-assessment' (previously 'agentic-dev-team' and 'agentic-security-assessment'). The 'agentic-' prefix carried no information — every plugin in this marketplace is agentic by definition.

### Features

* **upgrade:** migrate legacy agentic-* plugin ids on upgrade ([f6865fc](https://github.com/bdfinst/agentic-dev-team/commit/f6865fc2735b14424118de2fc2ca51a1831283c9))


### Code Refactoring

* **agents:** orchestration cluster has no remaining sweep work (12c) ([a7c3211](https://github.com/bdfinst/agentic-dev-team/commit/a7c321173bdc967dd56d53d4f867cef262c53726))
* **dev-team:** sweep internal references to dev-team ([5ce4ba8](https://github.com/bdfinst/agentic-dev-team/commit/5ce4ba831e2ff7d90caeba7e0c61334a6a3d0f7a))
* rename plugins to dev-team and security-assessment ([a36bba2](https://github.com/bdfinst/agentic-dev-team/commit/a36bba28a670e5855605cadf794a7b092b04f2ba))


### Documentation

* **readme:** document /upgrade right after the install section ([7411abf](https://github.com/bdfinst/agentic-dev-team/commit/7411abf9532e40c35010b6cac239bf07840732af))
* **repo-root:** sweep references; add Renamed plugins README notice ([49066fb](https://github.com/bdfinst/agentic-dev-team/commit/49066fbc619256a7b312dbb283d869c5676d25f8))

## [5.6.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.5.0...agentic-dev-team-v5.6.0) (2026-06-02)


### Features

* **hooks:** PostToolUse hook regenerates knowledge index + fail-open ([568ed0a](https://github.com/bdfinst/agentic-dev-team/commit/568ed0ae342543e4aee5d5c3b002190ea7b754af))
* **hooks:** pre-commit sibling hook + shared commit-detection helper ([4db7eba](https://github.com/bdfinst/agentic-dev-team/commit/4db7eba5793280861c0803d486cd1b4c95ae3307))
* **knowledge-index:** pin jq &gt;= 1.6 for stable output formatting ([f66ceca](https://github.com/bdfinst/agentic-dev-team/commit/f66cecaf8a5e7c3af1b5a422c5ff673d7e7b4f9a))
* **knowledge-index:** ship the initial knowledge/index.json ([4201181](https://github.com/bdfinst/agentic-dev-team/commit/42011814749ed20c89cf22ff6bda1acadd532b9c))
* **knowledge-index:** summary extraction with operational sentence boundary ([cd4fe65](https://github.com/bdfinst/agentic-dev-team/commit/cd4fe65a74f577caa13724d124669428a1426ece))
* on-demand knowledge index + 550× perf rewrite + agent rename ([4e680fc](https://github.com/bdfinst/agentic-dev-team/commit/4e680fc9a55b0e1738faf567ae8050ec600e6a18))


### Code Refactoring

* **agents:** cite knowledge anchors in code-quality cluster (12b) ([d2e50bc](https://github.com/bdfinst/agentic-dev-team/commit/d2e50bc0334e69a9bd008cd0678cb1b8d21ddb37))
* **agents:** cite knowledge anchors in security cluster (12a) ([9eb5a32](https://github.com/bdfinst/agentic-dev-team/commit/9eb5a32af7173acd818c23fe8f8eee80685c08f5))
* **agents:** orchestration cluster has no remaining sweep work (12c) ([a7c3211](https://github.com/bdfinst/agentic-dev-team/commit/a7c321173bdc967dd56d53d4f867cef262c53726))
* **agents:** rename files to match internal agent names ([1b6d304](https://github.com/bdfinst/agentic-dev-team/commit/1b6d30474e6d2c074888dc1ddbdb25144112283d))
* **agents:** rename refactoring-review → refactor-opportunity-review ([d602e69](https://github.com/bdfinst/agentic-dev-team/commit/d602e6922e38264d6f1aab2285ba83b4084683a5))


### Performance Improvements

* **knowledge-index:** rewrite builder inner loop as one Python process ([1f3c06c](https://github.com/bdfinst/agentic-dev-team/commit/1f3c06cfa13efd5ccd6bd10dd54ad6482911af27))


### Documentation

* capture knowledge indexing decision in ADR 0005; retire spec + plan ([f1b291a](https://github.com/bdfinst/agentic-dev-team/commit/f1b291a696283636407615b5ec3078fabc8cd2f2))
* **orchestrator:** document the index lookup → section Read consumer pattern ([f299182](https://github.com/bdfinst/agentic-dev-team/commit/f2991829078217f9d942fc51887ac69013be1418))

## [5.5.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.4.0...agentic-dev-team-v5.5.0) (2026-06-01)


### Features

* **commands:** add /model-routing-check diagnostic ([5aa05fc](https://github.com/bdfinst/agentic-dev-team/commit/5aa05fcc6b396455d636f5a1d11cf1aa2c4d8b4a)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* environment-aware model routing with PreToolUse hook enforcement ([511ec58](https://github.com/bdfinst/agentic-dev-team/commit/511ec58fc86a141c3f280ccc5cf8ae3209fdbfd8))
* **hooks:** add codegraph-nudge skeleton with .codegraph/ presence check ([f0fbcf2](https://github.com/bdfinst/agentic-dev-team/commit/f0fbcf2a2b4bc860076da05b499b8aea27dab932))
* **hooks:** codegraph-nudge blocks in careful mode ([9c1ddf5](https://github.com/bdfinst/agentic-dev-team/commit/9c1ddf51c967b034e734a39bda2f14bbde0f3be1))
* **hooks:** codegraph-nudge warns on Grep/Glob multi-file shape ([fddaabd](https://github.com/bdfinst/agentic-dev-team/commit/fddaabde84bb28398264bd26363bae670b1335e5))
* **hooks:** PreToolUse Agent hook enforces pre-dispatch resolution ([ff937a2](https://github.com/bdfinst/agentic-dev-team/commit/ff937a20ac77c49a47a37568eb2778941cbdf7e4)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* **hooks:** register codegraph-nudge and codegraph-turn-mark in settings.json ([60f0fa0](https://github.com/bdfinst/agentic-dev-team/commit/60f0fa0f69acd3c276300d4c84113eb95df441af))
* **hooks:** sentinel-based turn-boundary detection for codegraph-nudge ([9115852](https://github.com/bdfinst/agentic-dev-team/commit/911585268e52e9be2f142e0dee960d3ff47fadde))
* **init-dev-team:** opt-in probe of /v1/models with three failure modes ([d3fc9ec](https://github.com/bdfinst/agentic-dev-team/commit/d3fc9ec77aa4add6b50f3d88bdfdc1cee1be0c5c)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* **init:** bootstrap JS project via js-project-init when no package.json ([8853172](https://github.com/bdfinst/agentic-dev-team/commit/8853172c294889cef64fc84012c5eb4833f8704e))
* **init:** state-aware CodeGraph step in /init-dev-team ([10a62cf](https://github.com/bdfinst/agentic-dev-team/commit/10a62cf1b7681eb9ff3b9e233058eb45e36905cc))
* **knowledge:** add adversarial review protocol, design smells, object calisthenics, testability patterns ([d3fe547](https://github.com/bdfinst/agentic-dev-team/commit/d3fe5470609cf69272de830753eecf551ed31f53))
* **knowledge:** adversarial review protocol, design smells, object calisthenics, testability patterns ([b75b8ec](https://github.com/bdfinst/agentic-dev-team/commit/b75b8ecfbd0b5abb8bfc68546dfbf2695766f218))
* **model-resolve:** happy-path tier→snapshot resolution ([7affb2b](https://github.com/bdfinst/agentic-dev-team/commit/7affb2b72098a1cc8565cc4b523b65866983d625)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* **model-resolve:** overrides, cascade, cycle, exhaustion, dump-map ([3557378](https://github.com/bdfinst/agentic-dev-team/commit/3557378a10c4f9ddca3e6cb5511fda86748f1b58)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* **model-resolve:** perf gate + happy-path fast-path ([069cfb6](https://github.com/bdfinst/agentic-dev-team/commit/069cfb6ca5d868782bb59b3d93a234d3e3fb672b)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* **model-routing:** ship knowledge/model-routing.json defaults ([e326cc1](https://github.com/bdfinst/agentic-dev-team/commit/e326cc19a416e80a6a6967a164f1ef9f43f6dd4b)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* **skills:** add adr-tools skill for npryce/adr-tools CLI mechanics ([f0cce9d](https://github.com/bdfinst/agentic-dev-team/commit/f0cce9d940c5f7809e566e01416c40ce552e3537))
* **skills:** add mermaid-diagramming skill with blue-gray theme ([f909895](https://github.com/bdfinst/agentic-dev-team/commit/f9098953d9038569858aebe8cdd4e9b3c9606887))
* state-aware CodeGraph integration for init flows + PreToolUse nudge hook ([117a78e](https://github.com/bdfinst/agentic-dev-team/commit/117a78eaa2be17cd4458d0ab99f86d6fe3245229))
* **ux:** SessionStart hook surfaces routing overrides banner ([9150c43](https://github.com/bdfinst/agentic-dev-team/commit/9150c4383f40c75f1ccf3968175957779096d4db)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)


### Bug Fixes

* **hooks:** address inline-review findings ([3f39271](https://github.com/bdfinst/agentic-dev-team/commit/3f39271ca6079ff9a9421db9d05e67d7ae0c2c28))
* move ADRs to docs/adr/ to match project convention ([d568765](https://github.com/bdfinst/agentic-dev-team/commit/d56876551c057c1c7a8b9ef41f68b1f3a023efd4))
* **review:** address code-review findings before PR ([36f1b57](https://github.com/bdfinst/agentic-dev-team/commit/36f1b5737e8648e1d0452df18b3ae682577b1cd4))


### Code Refactoring

* **orchestrator:** relocate model routing authority to PreToolUse hook ([66bca9f](https://github.com/bdfinst/agentic-dev-team/commit/66bca9f7865c3cf92d5e4893159dc8f23a5fc335)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)


### Documentation

* **adr:** pre-dispatch model resolution + hook enforcement decisions ([aa52c37](https://github.com/bdfinst/agentic-dev-team/commit/aa52c37069e110c45604a15aeda53ec4582b3ec7)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* complete the hook-as-authority sweep + fix probe invocation path ([0701731](https://github.com/bdfinst/agentic-dev-team/commit/0701731340f133102befe686cfa7ed168fa9c98b)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* complete the routing-doc cleanup + add architecture diagrams ([2ab3725](https://github.com/bdfinst/agentic-dev-team/commit/2ab372545b0840761c7055cad31b90ce042e2181)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
* document codegraph-nudge hook and updated init-dev-team flow ([414f67b](https://github.com/bdfinst/agentic-dev-team/commit/414f67b286c368063355dc4427764c09e519b6d2))
* fix CHANGELOG ([0f7fd09](https://github.com/bdfinst/agentic-dev-team/commit/0f7fd09bcf68cc8cba79f72a2189b0101bd0581b))
* mention codegraph-nudge in agent-architecture and reference ([3de9e94](https://github.com/bdfinst/agentic-dev-team/commit/3de9e949a78ad8c871243f8c4ac51476040b661c))
* model routing contract and troubleshooting guide ([dc4bd03](https://github.com/bdfinst/agentic-dev-team/commit/dc4bd036f75a4a7e4e4bf9ca55542c939e99a8ad)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)


### Miscellaneous

* remove pinned snapshot IDs outside routing.json ([1d5f133](https://github.com/bdfinst/agentic-dev-team/commit/1d5f13398fe0982cdffb7677c3651d40528e88ce)), closes [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)

## [5.4.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.3.1...agentic-dev-team-v5.4.0) (2026-05-28)


### Features

* **command:** add /init-dev-team command and update advisory messages ([62b9648](https://github.com/bdfinst/agentic-dev-team/commit/62b96489c79cc5fe00ed55c66f8b056c5e97a77a))
* **command:** add Windows support to /init-dev-team ([179874c](https://github.com/bdfinst/agentic-dev-team/commit/179874c9936869bf78ffcc5437009bd0aa3509a6))
* **hook:** add jq and python3 hard dependency guards ([cbdb518](https://github.com/bdfinst/agentic-dev-team/commit/cbdb5181ddf17e0b7cc03b90e0a40916b3e0e78c))
* **hook:** blocking output, exit codes, and end-to-end JS/TS flow ([534ae66](https://github.com/bdfinst/agentic-dev-team/commit/534ae669308fe10cd174aaa504d1f954458269f4))
* **hook:** language adapter dispatch with explicit adapter contract ([3a9312b](https://github.com/bdfinst/agentic-dev-team/commit/3a9312b691a61cc86f2bab8771bd83854f9052a4))
* **hook:** mutation-gate scaffold with fast-path, opt-out, and _timeout() ([60b092e](https://github.com/bdfinst/agentic-dev-team/commit/60b092ee03b73e5711c05d17fedf33aabfd58485))
* **hook:** pitest Java adapter with runner-stdout test-list derivation ([32b235f](https://github.com/bdfinst/agentic-dev-team/commit/32b235f5887383424fd75acb096ee1a66b6d19f1))
* **hook:** RED-GREEN transition detection with state file and stdout capture ([92862a6](https://github.com/bdfinst/agentic-dev-team/commit/92862a66cdf81bcdc5df0483129cdca79b030169))
* **hook:** register mutation-gate in PostToolUse Bash hook chain ([a785606](https://github.com/bdfinst/agentic-dev-team/commit/a7856069348cbdc549d3e79ef5e729ae6a80326b))
* **hook:** Stryker JS/TS adapter with fixture-based tests ([53e3684](https://github.com/bdfinst/agentic-dev-team/commit/53e36843da27d832bbdb0156f0c381de1bdc9458))
* **hook:** Stryker.NET C# adapter (reuses parse_stryker_kills from lib) ([c5221d4](https://github.com/bdfinst/agentic-dev-team/commit/c5221d408e97bb367786887774ff6c7a453e2359))


### Bug Fixes

* **hook:** address spec-compliance review findings ([baa072f](https://github.com/bdfinst/agentic-dev-team/commit/baa072f2e2142c6286b931e759bbca8ed4f36e92))


### Miscellaneous

* remove implemented plans and specs, add codegraph gitignore ([41e64d8](https://github.com/bdfinst/agentic-dev-team/commit/41e64d888c031a1b7cbf79022365cfe14b0b45dd))

## [5.3.1](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.3.0...agentic-dev-team-v5.3.1) (2026-05-15)

### Code Refactoring

* **agent-skill-authoring:** resolve overlap with agent-create skill ([2818bd5](https://github.com/bdfinst/agentic-dev-team/commit/2818bd5dd09d2e1b526cc7ea14fef274a86d0c26))

## [5.3.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.2.0...agentic-dev-team-v5.3.0) (2026-05-14)

### Features

* **agent-create:** add agent-create skill, official agent template, and schema validation ([e872244](https://github.com/bdfinst/agentic-dev-team/commit/e872244f91b1368109aac4db71b540bde9440b94))
* semantic-scan and agent-create skills with official schema validation ([cc1b6b3](https://github.com/bdfinst/agentic-dev-team/commit/cc1b6b378e3fc57c94abd33b72429a26ec236b51))
* **semantic-scan:** add /semantic-scan skill and command for detecting logical duplication ([324aea9](https://github.com/bdfinst/agentic-dev-team/commit/324aea949516883c2c9b942260e575f56da2afb4))

### Bug Fixes

* **agent-create:** move --dry check before file write; fix CLAUDE.md description ([7f93ef3](https://github.com/bdfinst/agentic-dev-team/commit/7f93ef34834d597710c8a3a245ddefaea234f73c))

## [5.2.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.1.1...agentic-dev-team-v5.2.0) (2026-05-12)

### Features

* add four missing subagent prompt templates ([6c86def](https://github.com/bdfinst/agentic-dev-team/commit/6c86defdbda261128a9452e6972fb55eaa8a3556))
* add Skill tool to agents with ## Skills sections ([c4eee0f](https://github.com/bdfinst/agentic-dev-team/commit/c4eee0f4c3a791a1d7e9d9c8c3f968f5932acf07))

### Code Refactoring

* **code-review:** trim command file, move templates to output-format ([6d04bbc](https://github.com/bdfinst/agentic-dev-team/commit/6d04bbc760e42a71d35f6c6b91f347d45c04c5ac))
* **context-loading-protocol:** drop stale token table, tighten ([1972508](https://github.com/bdfinst/agentic-dev-team/commit/1972508ed21b607abdd5398dd5845243888a2ac7))
* **docker-image-create:** tighten skill, keep runtime patterns inline ([cd7e686](https://github.com/bdfinst/agentic-dev-team/commit/cd7e686b559a1ac0eac6e469aaeaee7c4de965f6))
* **human-oversight-protocol:** cut philosophy, tighten ([8491232](https://github.com/bdfinst/agentic-dev-team/commit/849123270ef7483936db686496d876b56e053cd5))
* **js-project-init:** collapse defaults into a list, drop rationale prose ([a56257c](https://github.com/bdfinst/agentic-dev-team/commit/a56257cf7fee8a4f4db67a076be8947c7dfe1d64))
* **mutation-testing:** drop overlap with constraints, trim ([1e2ae4c](https://github.com/bdfinst/agentic-dev-team/commit/1e2ae4c3d034735322d45c36bbfb4e7b0926ea99))
* **performance-benchmark:** trim skill, move report template to examples ([553a107](https://github.com/bdfinst/agentic-dev-team/commit/553a1071036594a6ec49320d37d656e72058ff00))
* remove command wrappers and realign model routing ([faf1cd8](https://github.com/bdfinst/agentic-dev-team/commit/faf1cd89b02206f7f82bdd8c2a1bac1b5868b3c6))
* **specs:** merge Constraints + Guidelines into one Rules list ([ccff2d4](https://github.com/bdfinst/agentic-dev-team/commit/ccff2d49c241b6e1a88ff74dde9b29bb43b446f3))
* **static-analysis-integration:** extract maintenance, trim runtime skill ([67ee544](https://github.com/bdfinst/agentic-dev-team/commit/67ee54403162e592cec98d1dad8d2bee10a85c43))
* tighten team agent prompts and add output discipline ([0f36139](https://github.com/bdfinst/agentic-dev-team/commit/0f361395a29ca8b238f03acba2c6eacab3f8404d))

### Documentation

* add /explore spec, implementation plan, and exploratory-testing field guide ([5f1ffec](https://github.com/bdfinst/agentic-dev-team/commit/5f1ffecedd0f0a60aa14ac1bf2759dd3e5ad76e6))
* add /triage file-based output spec and implementation plan ([58b423f](https://github.com/bdfinst/agentic-dev-team/commit/58b423fde04a7f578cc85231b2c37676ec85fb90))

## [5.1.1](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.1.0...agentic-dev-team-v5.1.1) (2026-05-06)

### Code Refactoring

* rename devops-sre-engineer to platform-engineer and fix doc drift ([9d63904](https://github.com/bdfinst/agentic-dev-team/commit/9d6390466a92a3162b086210e5c4b5a0d2dc08e7))

## [5.1.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v5.0.0...agentic-dev-team-v5.1.0) (2026-04-27)

### Features

* **security-assessment:** ship apply-accepted-risks.sh + primitives contract v1.3.0 ([caa62df](https://github.com/bdfinst/agentic-dev-team/commit/caa62dfa668f16736257d8fd004443da7800027e))

## [5.0.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v4.0.0...agentic-dev-team-v5.0.0) (2026-04-24)

### ⚠ BREAKING CHANGES

* the `/data-scientist` slash command and data-scientist team agent have been removed. Consumers should migrate to `/software-engineer` or `/architect`.

### Features

* **recon:** add optional file_inventory to envelope schemas (contract 1.2.0) ([5dc9ffe](https://github.com/bdfinst/agentic-dev-team/commit/5dc9ffeb4c4754bdc791df699e0f0254eed55012))
* **recon:** canonical inventory enumeration script + ts-monorepo fixture ([9bf2ded](https://github.com/bdfinst/agentic-dev-team/commit/9bf2ded99b2477161ee3f8cf59426f06e020eaa0))
* remove data-scientist agent and overhaul plugin docs ([a91d7e9](https://github.com/bdfinst/agentic-dev-team/commit/a91d7e907e275195b5100d6fefbc2c1bc69c74b4))
* **security-review:** adapter error paths — malformed/unmapped category + missing category + bad mapping YAML ([c70cbd1](https://github.com/bdfinst/agentic-dev-team/commit/c70cbd1df4ebf995dceb05fb2bd754a601723cf4))
* **security-review:** adapter validates envelope schema + normalizes rule_id case + negative schema fixture ([6a81033](https://github.com/bdfinst/agentic-dev-team/commit/6a8103369bf3e0c8763763e419ba85f2c7b6c2a2))
* **security-review:** agent output schema + judgment-only OWASP category annotations + reliability eval ([095523d](https://github.com/bdfinst/agentic-dev-team/commit/095523d17c77554d07849c4ec7a428b41723427d))
* **security-review:** canonical rule_id mapping + adapter happy-path (language-specific included) ([02ce542](https://github.com/bdfinst/agentic-dev-team/commit/02ce542c339368b163c0f89609e6a31122f09bc5))

### Bug Fixes

* **recon:** align codebase-recon schema_version emission with 0.2 placeholder bump ([6558664](https://github.com/bdfinst/agentic-dev-team/commit/6558664218c6a64e2594ee71f1831a5c39135b0b))

### Code Refactoring

* **security-review:** strip pattern-visible classes from owasp-detection with pointer stubs (Item 3b) ([9af6355](https://github.com/bdfinst/agentic-dev-team/commit/9af635572cd843354030c40bc4f33f241e325c2f))

### Documentation

* **agentic-dev-team:** update cross-references to renamed companion plugin + history note on rename docs ([87a7a34](https://github.com/bdfinst/agentic-dev-team/commit/87a7a3445a26e2471ceff312fe34ecd92a3098de))
* **overlap-cleanup:** trigger-context section on security-review agent + reciprocal companion README note ([e6f5378](https://github.com/bdfinst/agentic-dev-team/commit/e6f5378368676d196a7a4bd1689e9f50c7d04f97))
* **recon:** contract 1.2.0 + codebase-recon Step 6.5 + fail-open consumer contract + pipeline budget ([af61d67](https://github.com/bdfinst/agentic-dev-team/commit/af61d672287e52ee8e03eb2b6101ece197828540))
* regenerate team-agents diagram for current roster ([1016411](https://github.com/bdfinst/agentic-dev-team/commit/10164118d7af035a27f15ecb188065b9b51da621))
* **security-review:** adapter docs + Phase 1b wiring + AST invariant + runtime smoke + backward-compat ([0522025](https://github.com/bdfinst/agentic-dev-team/commit/05220258912751fec5cc1c5473b0e848521b6689))
* **specs:** approved specs + plans for Item 5, Gap 6a, and plugin-rename ([764aa3b](https://github.com/bdfinst/agentic-dev-team/commit/764aa3b09ef2ee6491b65a560ca201ae1fce3c4c))

## [4.0.0](https://github.com/bdfinst/agentic-dev-team/compare/agentic-dev-team-v3.3.0...agentic-dev-team-v4.0.0) (2026-04-22)

### ⚠ BREAKING CHANGES

* skill file paths changed from skills/foo.md to skills/foo/SKILL.md. Team agent count reduced from 12 to 11.

### Features

* add baked-in config, Swiss Army Knife, and stateful container checks to docker-image-audit ([eefe5a8](https://github.com/bdfinst/agentic-dev-team/commit/eefe5a81349b2529dfcb97138d7f49a379a9f519))
* add codebase-recon agent with git history overview ([577cf98](https://github.com/bdfinst/agentic-dev-team/commit/577cf98140917ec849ca363d5c7f33c63ac0cb54))
* add default permissions to auto-approve most tools ([440407c](https://github.com/bdfinst/agentic-dev-team/commit/440407ce91952e64a7d32dd4f515ac697772519f))
* add docker-image-create and docker-image-audit skills ([7e115c8](https://github.com/bdfinst/agentic-dev-team/commit/7e115c8697aeab02a82c4b4dee49001ac8636502))
* add feature-file-validation skill to test-review pipeline ([5f53264](https://github.com/bdfinst/agentic-dev-team/commit/5f53264e3a35be53942958128ac80829937a6eb7))
* add plan review personas, performance benchmarking, review-fix loop, and auto-scope ([682e7ec](https://github.com/bdfinst/agentic-dev-team/commit/682e7eca3a35b3f5c9e91df79fc6b9ad277a8a98))
* add static analysis pipeline integration to code-review ([c031b4f](https://github.com/bdfinst/agentic-dev-team/commit/c031b4fe41936060d82fe542042a03ffc8633bb2))
* auto-trigger plan after spec approval and add BDD scenario review ([af99078](https://github.com/bdfinst/agentic-dev-team/commit/af990788855c13a8212cc37c1283d7b06ef30991))
* bump primitives contract to v1.1.0 + lift reference implementation details into plan ([edc02da](https://github.com/bdfinst/agentic-dev-team/commit/edc02dab75633fc5cf6e5b6e85e8b0d7193834f3))
* custom SARIF-emitting scripts — entropy-check + model-hash-verify ([b15762e](https://github.com/bdfinst/agentic-dev-team/commit/b15762ef03392be3cee552f43c7b1536f7fb3e9f))
* guard primitives-contract edits with semver-bump requirement ([730ccd1](https://github.com/bdfinst/agentic-dev-team/commit/730ccd113412c8e6272a46f496a0d61a50045521))
* **js-project-init:** add Husky pre-push hook and drop eslint-plugin-prettier ([119a71a](https://github.com/bdfinst/agentic-dev-team/commit/119a71a67c354478c05cdfd480377979f168f3b2))
* namespace plugin as agentic-dev-team@bfinster ([0a86eef](https://github.com/bdfinst/agentic-dev-team/commit/0a86eef6d5f795257eba4bdd98f8a77b933b9b54))
* persist /specs output to docs/specs/ after consistency gate passes ([69004a9](https://github.com/bdfinst/agentic-dev-team/commit/69004a9216756cfaaaa06c5cf0caa9a61d12562f))
* publish versioned security-primitives-contract v1.0.0 ([eed5bf5](https://github.com/bdfinst/agentic-dev-team/commit/eed5bf5c23c27c73d7534cadf9f5f5e397ea0d50))
* restructure skills into directories with progressive disclosure ([bab081b](https://github.com/bdfinst/agentic-dev-team/commit/bab081b448d540b4b378ea93bdbbbc6bbc0900d0))
* SARIF-first tool orchestration baseline (required 5 adapters) ([f5ed4fe](https://github.com/bdfinst/agentic-dev-team/commit/f5ed4fe2ad30bbbc59b5f873a9b5aa3c0860af7b))
* support ACCEPTED-RISKS.md project-local policy carveouts ([c40a16f](https://github.com/bdfinst/agentic-dev-team/commit/c40a16f5a137b145c2995d15e1a26a03fb734686))

### Bug Fixes

* **scope:** CI/CD workflow files explicitly in scope for static + security review ([763924f](https://github.com/bdfinst/agentic-dev-team/commit/763924fc7ad55f53b3ca96a19801f57e5badb390))
* update skill file references to include SKILL.md path ([90cd81d](https://github.com/bdfinst/agentic-dev-team/commit/90cd81dbaff644e320b7b40b58b915455f820da3))
* update skill file references to include SKILL.md path ([34a7474](https://github.com/bdfinst/agentic-dev-team/commit/34a74746bcfdcc64cc04998ad66f36b6387c68b3))
* use official claude plugin update mechanism in /upgrade command ([ab4c5d7](https://github.com/bdfinst/agentic-dev-team/commit/ab4c5d7c6b2b585e3cc0dedfc08dc959219c17a9))

### Code Refactoring

* **build:** remove canned summary template; trust native progress output ([8c2eb47](https://github.com/bdfinst/agentic-dev-team/commit/8c2eb4766291ca1786fda46b630166003fd5578e))
* move hook registrations to plugin settings.json ([95af67d](https://github.com/bdfinst/agentic-dev-team/commit/95af67d76a96572e9b551a52b7bafed59a55b4c5))
* move plugin components into plugins/agentic-dev-team/ ([b1a4792](https://github.com/bdfinst/agentic-dev-team/commit/b1a47920c4e92c8bf9e4513928668e0d66110eed))
* split CLAUDE.md into plugin config and dev instructions ([8157142](https://github.com/bdfinst/agentic-dev-team/commit/815714218bb63e62e3a9185b6caa3dade6d35c07))

### Documentation

* move per-plugin install instructions into each plugin's README ([26bca28](https://github.com/bdfinst/agentic-dev-team/commit/26bca280debae8d430bea0389a70caf8d1221400))

### Miscellaneous

* **main:** release 2.1.1 ([66b5ad9](https://github.com/bdfinst/agentic-dev-team/commit/66b5ad999dcf315818c3f8c8ab3f33e51d5ee85d))
* **main:** release 2.1.1 ([118ed58](https://github.com/bdfinst/agentic-dev-team/commit/118ed586a00393e9f84d5e3004081825ca6da996))
* **main:** release 2.2.0 ([ab37326](https://github.com/bdfinst/agentic-dev-team/commit/ab373265bffcdcad572da15cde1559e814ffe584))
* **main:** release 2.2.0 ([a35dad7](https://github.com/bdfinst/agentic-dev-team/commit/a35dad716f933a5b9fe49a11c7690a6b2e59e75c))
* **main:** release 2.3.0 ([7b5ebe7](https://github.com/bdfinst/agentic-dev-team/commit/7b5ebe78c22449b8d7dd5d2ef2f56a4a40719539))
* **main:** release 2.3.0 ([182a222](https://github.com/bdfinst/agentic-dev-team/commit/182a2225c3abc62259a38d29da36ebc18086867e))
* **main:** release 3.0.0 ([6825078](https://github.com/bdfinst/agentic-dev-team/commit/6825078428bffb0f65494686436ae3791be2cba8))
* **main:** release 3.0.0 ([8950366](https://github.com/bdfinst/agentic-dev-team/commit/8950366b622d32d1ce97766b792998bd949b0bca))
* **main:** release 3.1.0 ([8413514](https://github.com/bdfinst/agentic-dev-team/commit/841351484088fcf6fae2c474e57ad3035209a30b))
* **main:** release 3.1.0 ([36d22b6](https://github.com/bdfinst/agentic-dev-team/commit/36d22b68b1a6dbb95d925f4893988ae7e0c4e4c6))
* **main:** release 3.1.1 ([2e7db64](https://github.com/bdfinst/agentic-dev-team/commit/2e7db64b0a5cd1cce65f787980d6962fdb2cfa5a))
* **main:** release 3.1.1 ([4425e5d](https://github.com/bdfinst/agentic-dev-team/commit/4425e5db1a38c51e8c876d2f2f4363eba886f92a))
* **main:** release 3.2.0 ([cfbdd77](https://github.com/bdfinst/agentic-dev-team/commit/cfbdd774cc08100fea571c59099e7907cf3d86bd))
* **main:** release 3.2.0 ([6165507](https://github.com/bdfinst/agentic-dev-team/commit/6165507a303f6a3ecc43ff6182bb14be0f47c78c))
* **main:** release 3.3.0 ([766c71c](https://github.com/bdfinst/agentic-dev-team/commit/766c71ce3943d3d2e022c90f1e36b2afd971b6c5))
* **main:** release 3.3.0 ([c7b4597](https://github.com/bdfinst/agentic-dev-team/commit/c7b45974dbb471a18de72098757bf4b8a11aa7d3))

---

## Pre-Restructure History (v2.0.0–v3.3.0)

> These entries are from the root `CHANGELOG.md` that existed before the repository was restructured into a multi-plugin monorepo. Version tags in this section use the old `vX.Y.Z` format rather than the current `agentic-dev-team-vX.Y.Z` component-scoped format.

## [3.3.0](https://github.com/bdfinst/agentic-dev-team/compare/v3.2.0...v3.3.0) (2026-04-14)

### Features

* add default permissions to auto-approve most tools ([440407c](https://github.com/bdfinst/agentic-dev-team/commit/440407ce91952e64a7d32dd4f515ac697772519f))

### Bug Fixes

* update skill file references to include SKILL.md path ([90cd81d](https://github.com/bdfinst/agentic-dev-team/commit/90cd81dbaff644e320b7b40b58b915455f820da3))
* update skill file references to include SKILL.md path ([34a7474](https://github.com/bdfinst/agentic-dev-team/commit/34a74746bcfdcc64cc04998ad66f36b6387c68b3))

## [3.2.0](https://github.com/bdfinst/agentic-dev-team/compare/v3.1.1...v3.2.0) (2026-04-10)

### Features

* add plan review personas, performance benchmarking, review-fix loop, and auto-scope ([682e7ec](https://github.com/bdfinst/agentic-dev-team/commit/682e7eca3a35b3f5c9e91df79fc6b9ad277a8a98))
* replace Mermaid diagrams with styled SVG images ([0e11eb8](https://github.com/bdfinst/agentic-dev-team/commit/0e11eb87d6a8d94ce51c865131db9057fab5d78f))

### Bug Fixes

* add more bottom padding to three-phase workflow SVG ([151cfef](https://github.com/bdfinst/agentic-dev-team/commit/151cfef539329f162db44a454a098096e81495e0))
* align fail-loop arrow to enter TDD box from the left edge ([37c4aa8](https://github.com/bdfinst/agentic-dev-team/commit/37c4aa856153234781d9b0765d9125a312ceb113))
* clean up broken lines and misaligned arrows in three-phase SVG ([86f97e9](https://github.com/bdfinst/agentic-dev-team/commit/86f97e9e5ceb5df11844252ba899697620b443ba))
* compress three-phase workflow SVG to prevent GitHub clipping ([2032cc9](https://github.com/bdfinst/agentic-dev-team/commit/2032cc942a450444b7e0445347e65bd728bae36f))
* connect Gate 3 arrows directly to /pr and Learning Loop box tops ([99d2d32](https://github.com/bdfinst/agentic-dev-team/commit/99d2d32d40f251bca56149b897a3729b58ae0d9b))
* increase three-phase workflow SVG viewBox height to prevent clipping ([18441fd](https://github.com/bdfinst/agentic-dev-team/commit/18441fddd2d807da4d041d8b41a572e42b69e9f2))
* move human gates inline with last step of each phase ([2134bc5](https://github.com/bdfinst/agentic-dev-team/commit/2134bc541a5f28a841841cadb9fe1385b5fef9fc))
* replace T-junction with two direct lines to /pr and Learning Loop ([703515b](https://github.com/bdfinst/agentic-dev-team/commit/703515b715a710e05bbae2ca98792db7f637f142))

## [3.1.1](https://github.com/bdfinst/agentic-dev-team/compare/v3.1.0...v3.1.1) (2026-04-10)

### Bug Fixes

* use official claude plugin update mechanism in /upgrade command ([ab4c5d7](https://github.com/bdfinst/agentic-dev-team/commit/ab4c5d7c6b2b585e3cc0dedfc08dc959219c17a9))

## [3.1.0](https://github.com/bdfinst/agentic-dev-team/compare/v3.0.0...v3.1.0) (2026-04-10)

### Features

* auto-trigger plan after spec approval and add BDD scenario review ([af99078](https://github.com/bdfinst/agentic-dev-team/commit/af990788855c13a8212cc37c1283d7b06ef30991))

## [3.0.0](https://github.com/bdfinst/agentic-dev-team/compare/v2.3.0...v3.0.0) (2026-04-09)

### ⚠ BREAKING CHANGES

* skill file paths changed from skills/foo.md to skills/foo/SKILL.md. Team agent count reduced from 12 to 11.

### Features

* add baked-in config, Swiss Army Knife, and stateful container checks to docker-image-audit ([eefe5a8](https://github.com/bdfinst/agentic-dev-team/commit/eefe5a81349b2529dfcb97138d7f49a379a9f519))
* add docker-image-create and docker-image-audit skills ([7e115c8](https://github.com/bdfinst/agentic-dev-team/commit/7e115c8697aeab02a82c4b4dee49001ac8636502))
* restructure skills into directories with progressive disclosure ([bab081b](https://github.com/bdfinst/agentic-dev-team/commit/bab081b448d540b4b378ea93bdbbbc6bbc0900d0))

## [2.3.0](https://github.com/bdfinst/agentic-dev-team/compare/v2.2.0...v2.3.0) (2026-04-08)

### Features

* add feature-file-validation skill to test-review pipeline ([5f53264](https://github.com/bdfinst/agentic-dev-team/commit/5f53264e3a35be53942958128ac80829937a6eb7))
* namespace plugin as agentic-dev-team@bfinster ([0a86eef](https://github.com/bdfinst/agentic-dev-team/commit/0a86eef6d5f795257eba4bdd98f8a77b933b9b54))
* persist /specs output to docs/specs/ after consistency gate passes ([69004a9](https://github.com/bdfinst/agentic-dev-team/commit/69004a9216756cfaaaa06c5cf0caa9a61d12562f))

## [2.2.0](https://github.com/bdfinst/agentic-dev-team/compare/v2.1.1...v2.2.0) (2026-04-06)

### Features

* add static analysis pipeline integration to code-review ([c031b4f](https://github.com/bdfinst/agentic-dev-team/commit/c031b4fe41936060d82fe542042a03ffc8633bb2))
* **js-project-init:** add Husky pre-push hook and drop eslint-plugin-prettier ([119a71a](https://github.com/bdfinst/agentic-dev-team/commit/119a71a67c354478c05cdfd480377979f168f3b2))

## [2.1.1](https://github.com/bdfinst/agentic-dev-team/compare/v2.1.0...v2.1.1) (2026-04-02)

### Code Refactoring

* move hook registrations to plugin settings.json ([95af67d](https://github.com/bdfinst/agentic-dev-team/commit/95af67d76a96572e9b551a52b7bafed59a55b4c5))
* move plugin components into plugins/agentic-dev-team/ ([b1a4792](https://github.com/bdfinst/agentic-dev-team/commit/b1a47920c4e92c8bf9e4513928668e0d66110eed))
* point marketplace.json source to plugins/agentic-dev-team ([b5ee9b8](https://github.com/bdfinst/agentic-dev-team/commit/b5ee9b82354db9ddf324d27be928c6c77cf703ab))
* split CLAUDE.md into plugin config and dev instructions ([8157142](https://github.com/bdfinst/agentic-dev-team/commit/815714218bb63e62e3a9185b6caa3dade6d35c07))

## [2.1.0](https://github.com/bdfinst/agentic-dev-team/compare/v2.0.0...v2.1.0) (2026-04-02)

### Features

* add /version command to report installed plugin version ([712ee1e](https://github.com/bdfinst/agentic-dev-team/commit/712ee1ef4ada98d3b7eae5d2b90853c4e90a5765))

## [2.0.0](https://github.com/bdfinst/agentic-dev-team/compare/v1.2.16...v2.0.0) (2026-04-02)

### ⚠ BREAKING CHANGES

* The /beads command and beads skill are no longer available. Users relying on bd for task tracking should use memory/ progress files and /continue instead.

### Features

* add js-project-init skill for scaffolding JS projects ([e753742](https://github.com/bdfinst/agentic-dev-team/commit/e75374281edbcaaac5bdb4a1c60e74190917ead8))
* automated pre-commit code review gate ([67df646](https://github.com/bdfinst/agentic-dev-team/commit/67df64657bf415f9df2dabe20662f5892dac0122))
* remove beads task tracking from plugin ([fd2444f](https://github.com/bdfinst/agentic-dev-team/commit/fd2444fa817e6ad5ca52390b93c05b575afe1d5f))

### Bug Fixes

* prevent false positive on gitignored .env files in security-review ([cb2b002](https://github.com/bdfinst/agentic-dev-team/commit/cb2b0020454ae4cdab41af04ffa86bd86cba805a))

### Code Refactoring

* mutation testing skill to use real tools instead of academic estimation ([892168b](https://github.com/bdfinst/agentic-dev-team/commit/892168b7a5af5205493942b00accc65d6b375475))
