---
rules:
  - id: test-fixture-credentials
    rule_id: gitleaks.secrets.generic-api-key
    files:
      - "services/*/tests/**"
    rationale: >
      Test fixtures contain dummy credentials used only to drive auth-flow
      test cases. These paths are excluded from production bundles via the
      services' pyproject.toml / package.json exclusion rules. Suppressing
      here prevents CI noise while real hardcoded credentials in production
      paths remain caught.
    expires: 2026-10-21
    owner: security-team
    scope: finding
    broad: false

  - id: multistage-dockerfile-root-in-builder
    rule_id: hadolint.dockerfile.dl3002
    files:
      - "services/*/Dockerfile"
    rationale: >
      Multi-stage Dockerfiles legitimately run as root in the builder stage
      for apt-get / pip install. The FINAL stage is non-root (USER directive
      present). This rule suppression only applies when the finding is on
      the builder stage; hadolint reports both stages, the first of which
      is expected. Check the Dockerfile's FROM chain if uncertain.
    expires: 2026-10-21
    owner: security-team
    scope: finding
    broad: true   # matches on Dockerfile path — both stages — not ideal
---

# Accepted Risks — comparative-testing fixture

This file is consumed by the agentic-security-review plugin's `/code-review`
and `/security-assessment` pipelines. The equivalent for the
opus_repo_scan_test reference is `business_logic.md` — see that file for the
same carveouts expressed in the reference's format.

A correctly-working comparative test: both pipelines suppress findings that
match these rules AND both still surface the real findings on non-test paths.
