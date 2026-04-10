# Changelog

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
