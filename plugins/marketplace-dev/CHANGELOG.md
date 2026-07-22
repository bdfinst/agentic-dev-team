# Changelog

## [1.2.0](https://github.com/bdfinst/agentic-dev-team/compare/marketplace-dev-v1.1.1...marketplace-dev-v1.2.0) (2026-07-22)


### Features

* add agent-contract validator for frontmatter compliance ([0224d27](https://github.com/bdfinst/agentic-dev-team/commit/0224d274a29e6b54562a6d87359d20cd2ac7469b))
* generate native model/effort frontmatter in agent-create/agent-add/plugin-audit ([640dc21](https://github.com/bdfinst/agentic-dev-team/commit/640dc212e21aee5da98df5a6ec404cba1a019ff0))


### Documentation

* generate the MkDocs nav from the docs tree via awesome-pages ([70319b3](https://github.com/bdfinst/agentic-dev-team/commit/70319b3c176f9d9a67fa3e090aa15568f27ba3c9)), closes [#1280](https://github.com/bdfinst/agentic-dev-team/issues/1280)


### Miscellaneous

* move non-contract keys (cites, scope, enforcement) out of agent frontmatter into the body ([dc9ea06](https://github.com/bdfinst/agentic-dev-team/commit/dc9ea066a322c33988815e90b799821f8322d567)), closes [#1333](https://github.com/bdfinst/agentic-dev-team/issues/1333)

## [1.1.1](https://github.com/bdfinst/agentic-dev-team/compare/marketplace-dev-v1.1.0...marketplace-dev-v1.1.1) (2026-07-20)


### Documentation

* sync marketplace-dev docs to code and refresh builder/cloud guides ([a6c61fc](https://github.com/bdfinst/agentic-dev-team/commit/a6c61fc5be083450746ad253ab4097f87bada517))

## [1.1.0](https://github.com/bdfinst/agentic-dev-team/compare/marketplace-dev-v1.0.0...marketplace-dev-v1.1.0) (2026-07-08)


### Features

* implement open issues batch (autoship, co-evolution, nav, audit) ([c57c533](https://github.com/bdfinst/agentic-dev-team/commit/c57c5332a8ede2689aef1d1460e2ee34f38aee2b)), closes [#1065](https://github.com/bdfinst/agentic-dev-team/issues/1065) [#1066](https://github.com/bdfinst/agentic-dev-team/issues/1066) [#1067](https://github.com/bdfinst/agentic-dev-team/issues/1067) [#1068](https://github.com/bdfinst/agentic-dev-team/issues/1068) [#1069](https://github.com/bdfinst/agentic-dev-team/issues/1069) [#1070](https://github.com/bdfinst/agentic-dev-team/issues/1070) [#1071](https://github.com/bdfinst/agentic-dev-team/issues/1071)


### Documentation

* documentation overhaul for all three plugins ([d2e5caf](https://github.com/bdfinst/agentic-dev-team/commit/d2e5cafe0789ae39c9bb5a3393bd933d3c04da01))

## [1.0.0](https://github.com/bdfinst/agentic-dev-team/compare/marketplace-dev-v0.1.0...marketplace-dev-v1.0.0) (2026-06-26)


### ⚠ BREAKING CHANGES

* the agent-create, agent-skill-authoring, agent-add, agent-remove, and add-plugin skills are removed from dev-team (hard cut) and now live in marketplace-dev. dev-team registry, CLAUDE.md, docs, orchestrator, tech-writer, and knowledge index updated accordingly. The agent-create effort test is repointed to the migrated skills. agent-audit remains in dev-team.

### Features

* add marketplace-dev plugin and migrate plugin-authoring skills from dev-team ([#464](https://github.com/bdfinst/agentic-dev-team/issues/464)) ([770e386](https://github.com/bdfinst/agentic-dev-team/commit/770e386270617517074dc6e06e16bf80d7336f64))


### Code Refactoring

* **agents:** orchestration cluster has no remaining sweep work (12c) ([a7c3211](https://github.com/bdfinst/agentic-dev-team/commit/a7c321173bdc967dd56d53d4f867cef262c53726))
