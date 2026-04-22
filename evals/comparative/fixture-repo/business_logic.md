# Business Logic — reference's suppression convention

This file is the `opus_repo_scan_test` reference's equivalent of
`ACCEPTED-RISKS.md`. It declares business decisions that have been reviewed
and accepted; the reference's `generate-12-security-report.md` agent
suppresses findings that match these items.

Mirrors the two carveouts in `ACCEPTED-RISKS.md` (adjacent file) in the
format the reference agents expect.

---

## Accepted: Test-fixture credentials

**Scope**: Files under `services/*/tests/` that declare hardcoded credential
constants used only to drive authentication test cases.

**Status**: Not Critical

**Justification**: These paths are excluded from production bundles by the
services' build configuration (pyproject.toml / package.json exclusion rules).
The credentials never reach deployed environments.

**Review date**: 2026-04-21
**Next review**: 2026-10-21
**Owner**: security-team

---

## Accepted: Multi-stage Dockerfile root-in-builder

**Scope**: `services/*/Dockerfile` rule `DL3002` (hadolint) — running as root
in the build stage.

**Status**: Not Critical

**Justification**: Multi-stage Dockerfiles run apt-get / pip install as root
in the builder stage, then switch to a non-root user in the final stage
(USER directive present). The finding on the builder stage is expected; the
finding on the final stage must remain caught if it re-appears.

**Review date**: 2026-04-21
**Next review**: 2026-10-21
**Owner**: security-team
