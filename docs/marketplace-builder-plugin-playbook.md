# Playbook: building a plugin that builds plugin marketplaces

A field guide for authoring a Claude Code **meta-plugin** — a plugin whose job is
to scaffold, audit, and maintain *plugin-marketplace monorepos*. It distills the
conventions this repo converged on (see the commit trail referenced throughout)
into a reusable blueprint: the marketplace anatomy your plugin must understand,
the skills/commands it should provide, the invariants it must enforce, and how to
build and test the plugin itself.

> Scope: this is about building the **tool** (a marketplace-builder plugin), not a
> single marketplace. For a one-off hardening pass on an existing marketplace, use
> `docs/` companion material / the `shipped_script_refs_test.bats` sensor directly.

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
      "version": "6.7.0",
      "source": {
        "source": "git-subdir",
        "url": "https://github.com/<org>/<repo>.git",
        "path": "plugins/dev-team",
        "ref": "dev-team-v6.7.0"
      }
    }
  ]
}
```
Key invariant: each catalog entry's `version` and `source.ref` must stay in lock-step
with the plugin's own `plugin.json` version and its release tag. Do **not** hand-edit
these — automate them (§6).

### 2.2 The manifest — `plugins/<name>/.claude-plugin/plugin.json`
`name`, `version`, `description`, optional `depends-on` (companion plugins) and a
contract version when plugins share a primitives contract.

### 2.3 Shipped vs not-shipped (the load-bearing distinction)
| Ships (under `plugins/<name>/`) | Never ships (repo root) |
|---|---|
| `agents/ skills/ commands/ hooks/ knowledge/ templates/ prompts/` | `tests/` (all bats + `*.test.sh` + fixtures) |
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
repo (cited in §7) rather than inventing the format.

---

## 4. The enforcement sensor it must ship/scaffold

The backbone is a `bats` sensor that auto-discovers `plugins/*` and proves four
invariants. `/new-marketplace` drops it into the repo-root test tree and wires it
into CI; `/audit-plugin` runs it. The four invariants:

1. **Every `${CLAUDE_PLUGIN_ROOT}/<file>` reference resolves** inside the same
   plugin (discoverability once installed).
2. **No shipped file escapes its plugin** via `${CLAUDE_PLUGIN_ROOT}/../..`
   (resolves in the dev monorepo, breaks once installed) — minus an explicit
   maintainer allowlist.
3. **Every `settings.json` hook command resolves** to a shipped file. (Hooks run
   from the plugin root, so the bare `bash hooks/x.sh` form is correct here.)
4. **No build/test tooling ships inside a plugin** (`*.test.sh`, `*.bats`,
   `run-all*.sh`, a `tests/` dir, …).

A portable, parameterized implementation lives in the hygiene kit
(`shipped_script_refs_test.bats`); ship that as the plugin's reference template.

---

## 5. Invariants to bake into every generated/audited plugin

Encode these as knowledge the plugin's skills enforce — they are the difference
between "a plugin" and "a healthy, tested plugin."

- **Shipping hygiene.** Runtime files only under `plugins/<name>/`; tests/build at
  repo root. Reference every executed helper as `${CLAUDE_PLUGIN_ROOT}/<path>`.
  Scripts the plugin actually runs at runtime **must** ship *and* be discoverable
  (both halves matter — see the build-wave scripts fix, `#261`, and the
  discoverability fix, `#263`).
- **Portability — macOS bash 3.2 / BSD coreutils / Windows Git Bash.** All shell
  is `#!/usr/bin/env bash` and must run on all three:
  - bash 3.2-safe: no `mapfile`/`readarray`, `declare -A`, `${var,,}`, `wait -n`;
    expand possibly-empty arrays with `${arr[@]+"${arr[@]}"}` (bare `"${arr[@]}"`
    under `set -u` aborts on 3.2 — and CI on bash 5 won't catch it; cf. `#220`).
  - BSD-vs-GNU: guard or avoid `readlink -f`, `sed -i`, `date +%N`, `stat -c`,
    `find -printf`, `timeout`, `base64 -w` with fallbacks (cf. `#197`).
  - Windows = Git Bash; each `install.sh` detects Windows-without-Git-Bash and
    tells the user to install it (native cmd/PowerShell are not targets).
  - Python invoked as a module: make it cwd-independent and spawn cross-platform
    (`subprocess`, not `os.exec*`).
- **Tested.** Ship a bats sensor (§4) + targeted unit/smoke tests; wire them into
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

## 6. Release + catalog sync (automate, never hand-edit)

`release-please` with one `package` per plugin and `extra-files` that rewrite the
catalog entry on every release — so `plugin.json`, the tag, and `marketplace.json`
can never drift (cf. `#210`):

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

## 7. Building the plugin itself (step by step)

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
4. **Ship the sensor + a self-test.** Include `shipped_script_refs_test.bats` as a
   template and add a test that runs it against a fixture marketplace to prove the
   scaffolder produces a passing repo.
5. **Wire CI + dev-setup for the plugin's own repo.** Structural gate, portability
   sweep, bats sensor, and `scripts/dev-setup.sh`.
6. **Add `install.sh` (with the Git-Bash guard) and `CLAUDE.md`.** Document what
   each `/command` does and the conventions it enforces.
7. **Release via release-please** with the catalog `extra-files` sync (§6).

### Reference templates (this repo)
| Pattern | Canonical file(s) here |
|---|---|
| Catalog | `.claude-plugin/marketplace.json` |
| Manifest + deps | `plugins/security-assessment/.claude-plugin/plugin.json` |
| Hygiene sensor | `tests/repo/shipped_script_refs_security_assessment_test.bats` |
| Portability fallbacks | `plugins/dev-team/scripts/recon-inventory.sh`, `plugins/security-assessment/scripts/_lib.sh`, `plugins/dev-team/hooks/mutation-adapters/lib.sh` |
| Git-Bash `install.sh` guard | `plugins/dev-team/install.sh`, `plugins/security-assessment/install.sh` |
| Toolchain installer | `scripts/dev-setup.sh` |
| Smoke test + CI job | `tests/security-assessment/harness/smoke_test.py`, `.github/workflows/plugin-tests.yml` (`harness-smoke`) |
| Release + catalog sync | `release-please-config.json`, `.release-please-manifest.json` |
| Cloud install hook | `.claude/install-dev-team.sh`, `.claude/settings.json` |
| CI gate layout | `.github/workflows/plugin-tests.yml`, `scripts/ci-local.sh` |

---

## 8. Acceptance checklist for the plugin you build

A marketplace produced (or audited-clean) by your plugin must pass all of:

- [ ] Every catalog entry maps to a `plugins/<name>/` with a `plugin.json`; versions/refs in sync.
- [ ] The hygiene sensor (§4) is green — no shipped test/build scripts, all refs discoverable.
- [ ] `shellcheck -x` clean (warning severity) over shipped + dev scripts; all shebangs `env bash`.
- [ ] Each `install.sh` has the Git-Bash-on-Windows guard; `scripts/dev-setup.sh` provisions the toolchain.
- [ ] CI runs structural + portability + bats gates; a local pre-push gate mirrors them.
- [ ] `release-please` wired with per-plugin packages + catalog `extra-files` sync.
- [ ] A gated `SessionStart` cloud hook + skill-file fallback exist.
