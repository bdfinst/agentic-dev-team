# Changelog

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
