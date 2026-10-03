# Experiment install harness

`scripts/experiment_install_harness.py` provisions the two isolated test
projects that A/B arms **B** (released plugin) and **C** (experiment-branch
plugin) of epic #1097 run in. The script installs the right dev-team build
into each project. It verifies that each project loaded the intended build.
It also emits a JSON manifest that records exactly what it installed where.
The harness exists so the Phase 3 executor (#1099) never re-derives the setup
by hand.

Epic #1097 has three phases. Phase 1 lands the experiment-branch content
(#1092/#1093 — `fanout-economics.md` knowledge and the orchestrator's
delegation-only sweep rule). Phase 2 (this harness, #1098) makes the release
and branch builds installable side by side. Phase 3 (#1099) executes the
measured A/B/C runs against the two provisioned projects.

## Prerequisites

- The `claude` CLI on `PATH` (any environment where `claude plugin …` works).
  The `--dry-run` flag does not need it.
- `git` on `PATH`. The harness uses `git` read-only, for `git rev-parse HEAD`.
  Without `git`, the harness warns and records a `null` SHA in the manifest.
- A local checkout of the marketplace repo at the **experiment branch**.
  This checkout is the treatment install source.
- Network access to GitHub for the control arm. The command `claude plugin
  marketplace add bdfinst/agentic-dev-team` clones the published marketplace.

## The one command

```bash
python3 scripts/experiment_install_harness.py \
  --workdir /tmp/exp-1097 \
  --experiment-checkout /path/to/experiment-branch-checkout
```

That single invocation does the following:

1. **Control (arm B)** — in `<workdir>/control-project`, with
   `CLAUDE_CONFIG_DIR=<workdir>/control-claude-config`, runs
   `claude plugin marketplace add bdfinst/agentic-dev-team` then
   `claude plugin install dev-team@bfinster`. This installs the released
   version. The harness records the release tag and the marketplace-clone SHA.
2. **Treatment (arm C)** — in `<workdir>/treatment-project`, with
   `CLAUDE_CONFIG_DIR=<workdir>/treatment-claude-config`, runs
   `claude plugin marketplace add <checkout>` then
   `claude plugin install --scope project dev-team@bfinster`. This installs
   the branch build. The harness records the branch SHA from
   `git rev-parse HEAD` in the checkout.
3. Runs the verification probe on both installs (below).
4. Writes the manifest to `<workdir>/experiment-manifest.json`.

Useful flags:

- `--control-only` and `--treatment-only` provision one side.
- `--dry-run` prints every command without executing. It works with no
  `claude` CLI, so use it in CI.
- `--manifest PATH` relocates the output.
- `--control-project`, `--treatment-project`, and `--*-config-dir` override the
  default layout.
- `--marker`, `--marker-string`, `--control-plugin-dir`, and
  `--treatment-plugin-dir` tune the probe.

Run `--help` for the full list.

**Why per-arm `CLAUDE_CONFIG_DIR` values:** Claude Code's plugin cache is
version-keyed (`<config>/plugins/cache/<marketplace>/dev-team/<version>/`).
Suppose a branch build has a `plugin.json` version string equal to the
release's. If both arms shared one `~/.claude`, the branch build would collide
with the released cache and silently reuse it. This is the staleness trap
documented in `evals/code-review-benchmark/README.md`. Separate config dirs
per arm remove the collision by construction. They also keep the executor's
personal `~/.claude` untouched.

## Manifest fields

The top level has these fields: `schema_version` (currently 1),
`generated_at` (UTC ISO-8601), `harness`, `epic` (`#1097`), `dry_run`, and
`arms`. The `arms` field holds `control` and/or `treatment` objects. Each arm
has these fields:

| Field | Meaning |
| --- | --- |
| `arm` / `role` | `"B"`/`"control"` or `"C"`/`"treatment"` |
| `project_dir` | The test project the arm's sessions must be opened in |
| `claude_config_dir` | The `CLAUDE_CONFIG_DIR` every `claude` invocation for this arm must use — sessions launched without it will load the executor's personal plugins instead |
| `plugin_id` | Installed plugin id (default `dev-team@bfinster`) |
| `install_source` | Marketplace slug (control) or checkout path (treatment) |
| `install_scope` | `user` (control) / `project` (treatment) |
| `commands` | The exact argv lists executed (or printed, in dry-run) |
| `executed` / `installed_at` | Whether the installs ran, and when (UTC) |
| `plugin_version` | From `installed_plugins.json`, falling back to the installed (or checkout) `.claude-plugin/plugin.json` |
| `resolved_sha` | Treatment: `git rev-parse HEAD` in the checkout. Control: HEAD of the cloned marketplace under `<config>/plugins/marketplaces/bfinster`, `null` if unavailable |
| `release_tag` | Control only, derived as `dev-team-v<version>` (the marketplace catalog's tag scheme) |
| `installed_plugin_dir` | Where the probe found the installed build |
| `probe` | See next section |
| `band_model_map` | **Recorded-at-runtime placeholder.** `bands` is `null` because `/model-routing-check` needs a live Claude Code session against the installed model ladder and is not automatable headlessly. The Phase 3 executor runs it once per arm (inside that arm's project + config dir) and records the mapping before measured runs. |

## Probe semantics

The probe deterministically answers: *did this project get the build it was
supposed to?* The experiment branch ships a marker that the release does not
have. By default the marker is the existence of `knowledge/fanout-economics.md`
inside the installed plugin root (added by #1092/#1093). The expectation per
arm is:

- **treatment** — marker **present** (`probe.passed: true` when found).
- **control** — marker **absent**. A marker present in control means the
  control project somehow got the branch build, so the probe fails.

The `--marker` flag swaps the relative path. The `--marker-string STR` flag
additionally requires the marker file to contain `STR`. Use it once the release
also ships the file and only its content differs.

The probe looks in these places, in order:

1. an explicit `--control-plugin-dir` / `--treatment-plugin-dir` override;
2. `installPath` from `<config>/plugins/installed_plugins.json`;
3. the newest entry under `<config>/plugins/cache/*/dev-team/*/`.

**Assumption:** the version-keyed cache layout in step 3
(`plugins/cache/<marketplace>/<plugin>/<version>/`) is what Claude Code
v2.1.x materializes. This layout depends on the version. If a future CLI
changes it, step 2 usually still resolves. Otherwise, pass the override flag.
In `--dry-run` the probe is skipped (`present` and `passed` are `null`).

## Interpreting failure

| Signal | Meaning | Action |
| --- | --- | --- |
| exit 3, "claude CLI is not on PATH" | Environment, nothing ran | Install Claude Code, or use `--dry-run` to preview |
| exit 1, "command … exited N" | An install command failed; its stdout/stderr were re-emitted verbatim just above | Read the CLI's own error (network, auth, bad marketplace path); re-run — fresh config dirs make the harness idempotent-ish, or point `--workdir` somewhere clean |
| exit 2, "probe FAILED … Wrong build loaded" | Installs succeeded but a project has the wrong build (e.g. control picked up a cached branch build, or the checkout is not on the experiment branch) | Check `resolved_sha` in the manifest against the expected branch head; wipe that arm's config dir and re-run |
| exit 2, "probe inconclusive — installed plugin dir not found" | Install reported success but the plugin didn't materialize where the harness looks | Locate it manually and pass `--control-plugin-dir`/`--treatment-plugin-dir` |
| `probe.passed: null` in a non-dry-run manifest | Same as above, in manifest form | Same |

A manifest with both arms at `probe.passed: true` is the green light for
Phase 3. Open each arm's sessions **inside its `project_dir` with its
`claude_config_dir` exported**. Run `/model-routing-check` to fill
`band_model_map.bands`. Then start the measured runs.

## Tests

`tests/scripts/test_experiment_install_harness.py` covers these areas:

- dry-run command construction for both arms
- manifest schema and content with mocked subprocesses
- probe present, absent, and inconclusive semantics
- installed-dir resolution

Run the tests with this command:

```bash
python3 -m pytest tests/scripts/test_experiment_install_harness.py -v
```
