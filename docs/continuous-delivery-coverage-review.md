# Continuous Delivery Coverage Review

A gap analysis of the dev-team plugin's skills and agents against Jez Humble &
David Farley, *Continuous Delivery: Reliable Software Releases through Build,
Test, and Deployment Automation* (Addison-Wesley, 2010; ISBN 0321670272).

## Method

Three passes: (1) inventory the plugin's CD-relevant skills, agents, and
knowledge from their actual contents; (2) extract a grounded practice checklist
from the book's six pipeline/release/data/version-control/maturity chapters;
(3) map one against the other. Findings are scoped to the plugin's purpose — a
plan / build / review / test harness with an advisory platform-engineer — not a
deployment runner.

## Verdict

The plugin is a **commit-stage powerhouse and a thin release stage**. It encodes
the left half of *Continuous Delivery* — testing strategy, the commit gate,
trunk-based development, build discipline — often more deeply than the book. It
barely touches the right half — deploy/release, infrastructure, data, the
maturity model. Some of that is correct scope. Several right-half gaps are *in
scope* because the plugin writes code (migrations) and advises on pipelines.

## Coverage map

| Book area | Plugin coverage | Verdict |
|---|---|---|
| Ch3 CI / Ch7 Commit stage | `cd-test-architecture`, deterministic pre-merge gate, `ci-debugging` (no retry-masking), TDD, mutation, Farley score | Strong |
| Ch4 Testing strategy | pyramid, quadrants, `test-strategy`, component/contract patterns | Strong |
| Ch8 Automated acceptance testing | Gherkin specs, ATDD core to `/plan`→`/build` | Strong |
| Ch14 Advanced version control | trunk-based (qa-engineer), commit discipline (progress-guardian), `branch-workflow` | Partial — branch-by-abstraction / expand-contract / feature-hiding to keep mainline releasable were missing |
| Ch2 Config management | twelve-factor template, `docker-image-audit` (secrets in ARGs) | Partial — no config-per-environment / secrets discipline as a first-class concern |
| Ch5 Pipeline anatomy | the test gate is strong | Gap — build-once/promote, smoke-test-every-deploy, deploy-the-same-way-everywhere, cycle-time-as-primary-metric were absent |
| Ch9 Capacity / nonfunctional | `performance-benchmark`, `benchmark` | Partial — present but not modeled as a gated stage |
| Ch10 Deploy & release | platform-engineer *named* blue-green/canary | Gap — named, not encoded; no rollback discipline, decouple-deploy-from-release, feature toggles |
| Ch12 Managing data | `database-test-patterns` (testing only) | Gap — no migration strategy: reversible expand/contract, schema versioning, decouple DB from app change (code-affecting) |
| Ch11 Infra / Ch13 Components | platform-engineer mentions IaC; docker CVE scan | Mostly out of scope for a code plugin (advisory only) |
| Ch15 Maturity model / value stream | DORA awareness (qa-engineer), agent-readiness scorecard (different axis) | Gap — no CD maturity / value-stream / cycle-time assessment |

## Gaps closed by this work

The follow-up change adds four knowledge bodies and wires them into the agents
that plan, build, and advise:

1. **Database change discipline (Ch12)** — `knowledge/database-change-management.md`:
   reversible expand/contract migrations, schema versioning (roll-forward +
   roll-back scripts), decouple DB change from app deploy, never destructive in a
   single step, backward/forward compatibility. Wired into software-engineer and
   architect; arch-review gains a migration-safety check via
   `architecture-assessment.md`.
2. **Release strategies (Ch10 + Ch14)** — `knowledge/release-strategies.md`:
   blue-green, canary, rolling, rollback-as-practiced, decouple deploy from
   release, feature toggles, branch by abstraction. Wired into platform-engineer
   and `/plan` (plan to keep mainline releasable).
3. **Pipeline anatomy + config (Ch5 + Ch2 + Ch11)** — `knowledge/deployment-pipeline.md`:
   build-once/promote the same artifact, env-agnostic binaries, deploy-the-same-way
   everywhere, smoke-test-every-deploy, single version-controlled config source per
   environment, secrets handling, cycle time as the primary metric, pipeline-as-product.
   Wired into platform-engineer.
4. **CD maturity model (Ch15)** — `knowledge/cd-maturity-model.md`: the six
   practice areas × five levels, the Deming improvement cycle, value-stream
   mapping, and the DORA outcome metrics. Wired into platform-engineer and
   qa-engineer; cross-linked to the agent-readiness scorecard (which measures a
   *different* axis — how agent-ready a repo is, not delivery capability).

## Deliberately out of scope

Advisory-only for a code plugin; not built here:

- **IaC authoring** (Terraform / Helm / CloudFormation generation) — platform-engineer
  advises on infrastructure-as-code patterns but the plugin does not generate stacks.
- **Artifact-repository management** (Artifactory / Nexus / registry operations).
- **Deploy orchestration execution** — the plugin recommends release strategies; it
  does not run blue-green/canary switches.

platform-engineer carries a one-line note that these are intentionally advisory.
