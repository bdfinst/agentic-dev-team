# Playbook: building a plugin that builds plugin marketplaces

A field guide for authoring a Claude Code **meta-plugin** — a plugin whose job is
to scaffold, audit, and maintain *plugin-marketplace monorepos*. It distills the
conventions this repo converged on (see the commit trail referenced throughout)
into a reusable blueprint: the marketplace anatomy your plugin must understand,
the skills/commands it should provide, the invariants it must enforce, and how to
build and test the plugin itself.

> **The concrete implementation lives in this repo: [`plugins/marketplace-dev/`](../plugins/marketplace-dev/README.md).**
> This playbook is the blueprint; `marketplace-dev` is the shipped meta-plugin
> that realizes it (scaffolding skills, the `plugin-audit` skill, and the
> `plugin-best-practices-review` agent). Read this for the *why*; read
> `marketplace-dev`'s own docs for the *what it does today*.

> Scope: this is about building the **tool** (a marketplace-builder plugin), not a
> single marketplace. For a one-off hardening pass on an existing marketplace, run
> the hygiene sensor ([`tests/repo/test_shipped_script_refs.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/tests/repo/test_shipped_script_refs.py))
> directly.

**On this page:** [1. What this plugin produces](#1-what-this-plugin-produces) ·
[2. Marketplace anatomy](#2-marketplace-anatomy-your-plugin-must-model) ·
[3. Skills & commands](#3-skills-commands-the-plugin-should-provide) ·
[4. The enforcement sensor](#4-the-enforcement-sensor-it-must-shipscaffold) ·
[5. Invariants to bake in](#5-invariants-to-bake-into-every-generatedaudited-plugin) ·
[6. Independent versioning + catalog sync](#6-independent-versioning-catalog-sync-automate-never-hand-edit) ·
[7. Cross-plugin dependencies](#7-cross-plugin-dependencies-plugin-a-consumes-plugin-b-at-a-pinned-version) ·
[8. Building the plugin itself](#8-building-the-plugin-itself-step-by-step) ·
[9. Acceptance checklist](#9-acceptance-checklist-for-the-plugin-you-build)

---

## 1. What this plugin produces

A healthy marketplace monorepo, every time:

```
.claude-plugin/marketplace.json     # the catalog (lists every plugin + its git-subdir source)
plugins/<name>/                     # one shipped plugin per dir
├── .claude-plugin/plugin.json      # manifest: name, version, description, depends-on
├── agents/  skills/  commands/     # behavioral surface (loaded on demand)
├── hooks/   settings.json          # PreToolUse/PostToolUse/SessionStart wiring
├── knowledge/ templates/ prompts/  # reference data + scaffolds
├── install.sh                      # prerequisite checker (ships)
└── CLAUDE.md                       # plugin instructions (ships)
tests/        scripts/              # gates + dev tooling — repo root, NEVER shipped
evals/  docs/  plans/               # corpus, dev docs, design — repo root, NEVER shipped
.github/workflows/                  # CI: structural + portability + tests
release-please-config.json          # automated versioning + catalog sync
requirements-dev.txt  scripts/dev-setup.sh
```

The plugin's value is that it bakes in the two hard-won facts about marketplaces:

1. **A plugin ships wholesale via its git-subdir `source`** — every tracked file
   under `plugins/<name>/` reaches end users. Build/test tooling inside that tree
   is shipped by accident.
2. **Installed plugins run with `${CLAUDE_PLUGIN_ROOT}` set, but the agent's cwd
   is the user's project, not the plugin root** — so a skill that runs a bare
   `scripts/x.sh` cannot find it once installed.

Everything below exists to make those two facts impossible to get wrong.

---

## 2. Marketplace anatomy your plugin must model

### 2.1 The catalog — `.claude-plugin/marketplace.json`

```json
{
  "name": "<owner-handle>",
  "owner": { "name": "..." },
  "plugins": [
    {
      "name": "dev-team",
      "version": "10.14.2",
      "source": {
        "source": "git-subdir",
        "url": "https://github.com/<org>/<repo>.git",
        "path": "plugins/dev-team",
        "ref": "dev-team-v10.14.2"
      }
    }
  ]
}
```

Key invariant: each catalog entry's `version` and `source.ref` must stay in lock-step
with the plugin's own `plugin.json` version and its release tag. Do **not** hand-edit
these — automate them (§6).

### 2.2 The manifest — `plugins/<name>/.claude-plugin/plugin.json`

`name`, `version` (this plugin's **own** independent semver — §6), `description`,
and — when plugins couple — `depends-on` (a per-companion **minimum-version**
floor) and `required-primitives-contract` (a semver **range** against a shared
versioned contract). The two dependency knobs are the subject of §7.

### 2.3 Shipped vs not-shipped (the load-bearing distinction)

| Ships (under `plugins/<name>/`) | Never ships (repo root) |
|---|---|
| `agents/ skills/ commands/ hooks/ knowledge/ templates/ prompts/` | `tests/` (pytest `test_*.py` + fixtures) |
| `settings.json install.sh CLAUDE.md` | `scripts/` (CI/eval/build tooling) |
| `harness/` (executable app code, if any) | `evals/ docs/ plans/ reports/` |

Your plugin must **refuse** to leave a test/build script inside a plugin dir, and
must reference every runtime helper as `${CLAUDE_PLUGIN_ROOT}/<path>` (§5).

---

## 3. Skills & commands the plugin should provide

Each is a user-invocable skill (`SKILL.md` with `user-invocable: true`). Build them
to emit files, run gates, and report — not to narrate.

| Command | Role | What it does |
|---|---|---|
| `/new-marketplace <owner>` | scaffold | Create `marketplace.json`, the repo-root `tests/ scripts/ docs/` trees, CI workflows, `release-please-config.json`, `requirements-dev.txt`, `scripts/dev-setup.sh`, the hygiene sensor test, and a root `CLAUDE.md` documenting the conventions. |
| `/add-plugin <name>` | scaffold | Create `plugins/<name>/` with the shipped dir skeleton, `plugin.json`, `install.sh` (with the Git-Bash check), `settings.json`, and `CLAUDE.md`; register it in the catalog and in `release-please-config.json` `packages` with the catalog `extra-files` sync. |
| `/audit-plugin [name]` | audit | Run the shipping-hygiene sensor (§4) + structural checks (every catalog entry has a dir, every dir has a manifest, versions in sync) + the portability sweep (§5). Report findings; offer fixes. |
| `/portability-check` | audit | `shellcheck -x` every shipped + dev script; flag bash-4/GNU-only constructs; verify shebangs; check the Git-Bash `install.sh` guard exists. |
| `/release-setup` | scaffold | Wire `release-please` with per-plugin `packages` and the `marketplace.json` `extra-files` jsonpath sync (§6). |
| `/cloud-setup` | scaffold | Generate the gated `SessionStart` install hook + `cloud-setup.sh` and the "use skills directly" fallback (see the companion cloud guide). |

Implementation note: model each skill on the matching artifact already in this
repo (cited in §8) rather than inventing the format.

---

## 4. The enforcement sensor it must ship/scaffold

The backbone is a **pytest** sensor that auto-discovers `plugins/*` and proves
four invariants. `/new-marketplace` drops it into the repo-root test tree and
wires it into CI; `/audit-plugin` runs it. (This repo's sensor was a `bats`
script originally; per [ADR 0014](adr/0014-python-for-cross-os-scripts.md) and
[ADR 0015](adr/0015-bash-removal-complete.md) the whole test/gate surface is now
Python — a new marketplace should start Python, not bash.) The four invariants:

1. **Every `${CLAUDE_PLUGIN_ROOT}/<file>` reference resolves** inside the same
   plugin (discoverability once installed).
2. **No shipped file escapes its plugin** via `${CLAUDE_PLUGIN_ROOT}/../..`
   (resolves in the dev monorepo, breaks once installed) — minus an explicit
   maintainer allowlist.
3. **Every `settings.json` hook command resolves** to a shipped file. (Hooks run
   from the plugin root, so the bare `python hooks/x.py` form is correct here.)
4. **No build/test tooling ships inside a plugin** (`*.test.sh`, `*.bats`,
   `test_*.py`, `run-all*`, a `tests/` dir, …).

A portable, parameterized implementation lives in the hygiene kit
([`tests/repo/test_shipped_script_refs.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/tests/repo/test_shipped_script_refs.py),
with the security-assessment variant at
[`tests/repo/test_shipped_script_refs_security_assessment.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/tests/repo/test_shipped_script_refs_security_assessment.py));
ship that as the plugin's reference template.

---

## 5. Invariants to bake into every generated/audited plugin

Encode these as knowledge the plugin's skills enforce — they are the difference
between "a plugin" and "a healthy, tested plugin."

- **Shipping hygiene.** Runtime files only under `plugins/<name>/`; tests/build at
  repo root. Reference every executed helper as `${CLAUDE_PLUGIN_ROOT}/<path>`.
  Scripts the plugin actually runs at runtime **must** ship *and* be discoverable
  (both halves matter — see the build-wave scripts fix, `#261`, and the
  discoverability fix, `#263`).
- **Portability — Python stdlib, cross-OS by construction.** Per
  [ADR 0014](adr/0014-python-for-cross-os-scripts.md) and
  [ADR 0015](adr/0015-bash-removal-complete.md), every shipped script in this
  repo's `plugins/dev-team/` is **Python 3.8+ using stdlib only** — it runs
  natively on macOS, Linux, and Windows with no Git Bash requirement. Prefer
  that for a new plugin:
  - Stdlib only, no `pip install` for shipped code (`subprocess`, `pathlib`,
    `argparse`, `json`, `re`, … cover most shell-script territory portably).
  - Probe OS-specific paths at runtime (`subprocess`, `pathlib`) rather than
    hard-coding macOS or Linux locations; spawn cross-platform (`subprocess`,
    not `os.exec*`) and stay cwd-independent.
  - The only surviving `.sh` are the **pre-Python bootstrap trampolines** that
    must run before an interpreter is guaranteed on `PATH` (`install.sh`, the
    `hooks/py.sh` resolver) — keep those `#!/usr/bin/env bash` and bash-3.2-safe,
    and keep the Windows-without-Git-Bash guard in each `install.sh`.
  - A **shell-based companion plugin** (this repo's `security-assessment` is one)
    still follows the old cross-shell rules for its own scripts: bash-3.2-safe
    (no `mapfile`/`declare -A`/`${var,,}`; expand possibly-empty arrays as
    `${arr[@]+"${arr[@]}"}`, cf. `#220`) and BSD-vs-GNU-guarded (`readlink -f`,
    `sed -i`, `stat -c`, `find -printf`, `timeout`, cf. `#197`).
- **Tested.** Ship a pytest sensor (§4) + targeted unit/smoke tests; wire them into
  CI as model-free gates; mirror them in a local pre-push gate; keep the gates
  parallel and fast (cf. `#247`). A runnable component (e.g. a harness) gets a
  lightweight smoke test + its own CI job.
- **Versioned + released.** Conventional commits → `release-please` → tag + catalog
  sync (§6). `/version` is a mechanical, deterministic lookup, not a guess
  (cf. `#259`).
- **Onboarding.** A `scripts/dev-setup.sh` that validates and installs the
  toolchain (brew/apt + `requirements-dev.txt`), and an `install.sh` prerequisite
  checker per plugin.
- **Cloud-aware.** A gated `SessionStart` install hook + a skill-file fallback so
  the plugin is usable in web sessions (see the companion cloud guide).

---

## 6. Independent versioning + catalog sync (automate, never hand-edit)

**Each plugin versions independently.** There is no repo-wide version. Every
plugin carries its own semver in `plugins/<name>/.claude-plugin/plugin.json` and
ships on its own cadence. `release-please` models this with **one `package` per
plugin** — each with its own `component`, `package-name`, tag prefix, and
`.release-please-manifest.json` entry — so a `fix:` that touches only
`plugins/dev-team/**` bumps *just* dev-team (→ tag `dev-team-vX.Y.Z`) and leaves
`security-assessment` at its current version. release-please attributes a commit
to a plugin by the **path it modifies**; a commit spanning two plugin dirs bumps
both, so keep commits plugin-scoped when you want independent bumps. (Tags are
`<component>-v<version>` via `include-component-in-tag` + `include-v-in-tag`.)

`extra-files` then rewrite the catalog entry on every release — so `plugin.json`,
the release tag, and `marketplace.json` can never drift (cf. `#210`):

```jsonc
"plugins/<name>": {
  "release-type": "simple",
  "package-name": "<name>",
  "component": "<name>",
  "extra-files": [
    ".claude-plugin/plugin.json",
    { "type": "json", "path": "/.claude-plugin/marketplace.json",
      "jsonpath": "$.plugins[?(@.name=='<name>')].version" },
    { "type": "json", "path": "/.claude-plugin/marketplace.json",
      "jsonpath": "$.plugins[?(@.name=='<name>')].source.ref" }
  ]
}
```

`/release-setup` generates this block per plugin and the matching
`.release-please-manifest.json` entry. `feat:` → minor, `fix:` → patch, `feat!:`/
`BREAKING CHANGE` → major.

---

## 7. Cross-plugin dependencies (plugin A consumes plugin B at a pinned version)

Once plugins version independently (§6), the question is how plugin **A** says
"I need plugin **B**, and not just any B." The naive answer — pin A to an exact
release of B — is the wrong one: B's version bumps for reasons that don't touch
A (internal refactors, unrelated features), so an exact pin forces needless
churn and tells you nothing about *what* A actually relies on. This repo uses
two complementary, coarse-to-fine mechanisms, both declared in A's
`plugin.json`:

### 7.1 `depends-on` — a presence + floor declaration (coarse)

A names the companion it needs and the **minimum** version that carries the
capability it relies on:

```json
"depends-on": [
  { "name": "dev-team", "minimum-version": "3.3.0" }
]
```

Use a **floor, never an exact pin**, so B can ship patches and additive features
without breaking A. This answers "is B installed, and is it new enough?" — it
does **not** describe the actual data/behavior A consumes. That's §7.2's job.

### 7.2 A versioned shared contract — the real coupling (fine; preferred)

Pin A to the *contract B publishes*, not to B's release number. The contract is
a **standalone versioned document** describing the exact surface the two plugins
exchange — data envelopes, JSON schemas, agent IDs, skill IDs — with its own
semver and its own semver *policy*. In this repo that's
`plugins/dev-team/knowledge/security-primitives-contract.md` (`version:` in
frontmatter). Consumers declare a semver **range**, not a point:

```json
"required-primitives-contract": "^1.0.0"
```

`^1.0.0` = "any `1.x`": accept PATCH (clarifications) and MINOR (additive — new
optional fields, new enum values, new agent/skill IDs) automatically; reject
MAJOR (renamed/removed fields, new required fields, changed semantics). The
contract's frontmatter spells out exactly what each level means so producers and
consumers share one rule.

Why this beats pinning to B's version: the contract **decouples the dependency
from B's release cadence**. B can refactor internals and ship unrelated features
freely; A only has to react when the *shared surface* changes — and a MAJOR bump
is the unambiguous, machine-checkable signal that it did. The contract is
versioned **independently** of either plugin: it does not ride dev-team's or
security-assessment's release number, even though it physically lives in the
producer's `knowledge/` tree.

### 7.3 Enforcement (make drift unmergeable)

- **Contract can't change silently.** A PreToolUse hook
  (`hooks/contract_version_guard.py`) blocks any *body* change to the contract
  file that doesn't also bump `version:` in its frontmatter, with a bypass only
  for release-please commits (and an audit-log entry on bypass). "Changed the
  shared surface but forgot to version it" therefore can't land by hand.
- **`/add-plugin`** writes a `depends-on` floor when a companion is named, and a
  `required-primitives-contract` range when the new plugin consumes a shared
  contract.
- **`/audit-plugin`** verifies, as blocker-level findings: (a) every
  `depends-on` names a plugin that exists in the catalog at a version `>=` the
  floor; (b) every `required-primitives-contract` range is **satisfiable by the
  contract's current `version:`** — a consumer stuck on `^1.0.0` after the
  contract moved to `2.0.0` is a hard failure that must be resolved by updating
  the consumer (and, if its behavior changed, bumping the consumer's own
  version per §6).

### 7.4 Which knob, when

| Need | Mechanism | Form |
|---|---|---|
| "B must be installed, and recent enough to have feature X" | `depends-on` | `minimum-version` floor |
| "A and B exchange data/IDs and must agree on its shape" | shared contract | `required-primitives-contract` semver **range** (`^1.x`) |
| "A relies on a specific B *release* artifact" | (avoid) — extract the shared surface into a contract instead | — |

Use them together: the `depends-on` floor guarantees B is present and roughly
current; the contract range guarantees the two actually agree on the wire.

---

## 8. Building the plugin itself (step by step)

1. **Bootstrap with your own conventions.** The marketplace-builder plugin is a
   plugin — so it must pass its own sensor. Lay it out as `plugins/marketplace-builder/`
   in a marketplace repo; put its tests at repo root.
2. **Author the knowledge base first.** A `knowledge/marketplace-conventions.md`
   that encodes §2–§6 (progressive disclosure: skills load it on demand). This is
   the plugin's "source of truth"; the skills reference it.
3. **Author the skills (§3).** Each `skills/<cmd>/SKILL.md` is a procedure that
   reads the conventions knowledge and emits/edits files. Templates for the files
   it scaffolds (catalog, plugin.json, CI, release config, sensor, install.sh,
   dev-setup) live under `templates/`.
4. **Ship the sensor + a self-test.** Include `tests/repo/test_shipped_script_refs.py`
   as a template and add a test that runs it against a fixture marketplace to prove
   the scaffolder produces a passing repo.
5. **Wire CI + dev-setup for the plugin's own repo.** Structural gate, portability
   sweep, pytest sensor, and `scripts/dev-setup.sh`.
6. **Add `install.sh` (with the Git-Bash guard) and `CLAUDE.md`.** Document what
   each `/command` does and the conventions it enforces.
7. **Release via release-please** with the catalog `extra-files` sync (§6).

### Reference templates (this repo)

| Pattern | Canonical file(s) here |
|---|---|
| Catalog | `.claude-plugin/marketplace.json` |
| Manifest + deps | `plugins/security-assessment/.claude-plugin/plugin.json` |
| Hygiene sensor (pytest) | `tests/repo/test_shipped_script_refs.py`, `tests/repo/test_shipped_script_refs_security_assessment.py` |
| Cross-OS Python (stdlib, no bash) | `plugins/dev-team/scripts/recon_inventory.py`, `plugins/dev-team/hooks/mutation_gate.py` |
| Residual shell fallbacks (companion plugin) | `plugins/security-assessment/scripts/_lib.sh` |
| Git-Bash `install.sh` guard (bootstrap shim) | `plugins/dev-team/install.sh`, `plugins/security-assessment/install.sh` |
| Toolchain installer | `scripts/dev-setup.sh` |
| Smoke test + CI job | `tests/security-assessment/harness/smoke_test.py`, `.github/workflows/plugin-tests.yml` (`harness-smoke`) |
| Release + per-plugin packages | `release-please-config.json`, `.release-please-manifest.json` |
| Manifest dependency declaration | `plugins/security-assessment/.claude-plugin/plugin.json` (`depends-on`, `required-primitives-contract`) |
| Versioned cross-plugin contract | `plugins/dev-team/knowledge/security-primitives-contract.md` |
| Contract version-bump guard | `plugins/dev-team/hooks/contract_version_guard.py` |
| Cloud install hook | `.claude/install-dev-team.sh`, `.claude/settings.json` |
| CI gate layout | `.github/workflows/plugin-tests.yml`, `scripts/ci-local.sh` |

---

## 9. Acceptance checklist for the plugin you build

A marketplace produced (or audited-clean) by your plugin must pass all of:

- [ ] Every catalog entry maps to a `plugins/<name>/` with a `plugin.json`; versions/refs in sync.
- [ ] The hygiene sensor (§4) is green — no shipped test/build scripts, all refs discoverable.
- [ ] `shellcheck -x` clean (warning severity) over shipped + dev scripts; all shebangs `env bash`.
- [ ] Each `install.sh` has the Git-Bash-on-Windows guard; `scripts/dev-setup.sh` provisions the toolchain.
- [ ] CI runs structural + portability + pytest gates; a local pre-push gate mirrors them.
- [ ] Each plugin versions **independently**: one `release-please` package per plugin (own component/tag/manifest entry) + catalog `extra-files` sync (§6).
- [ ] Every `depends-on` floor names a catalog plugin at a version `>=` the floor; every `required-primitives-contract` range is satisfiable by the contract's current `version:` (§7).
- [ ] Any shared cross-plugin contract is independently versioned and guarded against body-without-bump edits (§7).
- [ ] A gated `SessionStart` cloud hook + skill-file fallback exist.
