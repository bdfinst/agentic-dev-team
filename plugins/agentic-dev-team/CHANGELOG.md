# Changelog

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
