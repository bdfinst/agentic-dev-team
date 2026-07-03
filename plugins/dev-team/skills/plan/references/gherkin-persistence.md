# Resolving the Gherkin persistence decision

Procedure for `/plan` step 3: decide where each slice's Gherkin will
additionally be persisted as `.feature` files. The plan file remains the
authoring surface; the `.feature` files are derived copies, written only
after approval (step 6 of `SKILL.md`).

1. **Re-run?** If a plan file already exists at the resolved output path and
   already records a `**Gherkin persistence**:` decision in its metadata block,
   honor it — skip detection and every prompt below.
   Editing that line is the supported way to change the decision before a re-run.
2. **Detect the target project's BDD convention** — from the repo root, run:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect_bdd_convention.py
   ```

   Precedence is conservative — feature-files > manifest > none: existing
   `.feature` files beat a manifest dependency, and any ambiguity (multiple
   roots, conflicting destinations) reports `none`. A non-zero exit is treated
   as no-signal: surface the script's stderr in the run output and continue —
   planning never dies on a detection failure.
3. **Detected signal** → record the reported `dir` as the destination.
4. **No signal + interactive** → prompt the operator once:
   *"Persist Gherkin as .feature files? [y = features/<plan-slug>/ | n = plan file only | c = custom path]"*.
   Validate a `c` answer before recording it: the path must be repo-relative
   (not absolute, not outside the repository) and not under a vendored tree
   (`node_modules/`, `vendor/`, `dist/`, `build/`, virtualenvs). On an invalid
   path, state the rejection reason and re-prompt;
   the re-prompt accepts `y` or `n` as an escape from retrying a custom path.
5. **No signal + non-interactive** (the same triad step 6 uses: `--yes`,
   `DEV_TEAM_AUTO_APPROVE=1`, or no usable TTY) → do **not** block: log
   *"skipping the Gherkin persistence prompt (non-interactive) — plan file only"*
   and record `plan-file-only`.
6. **Record and echo.** Write the resolved decision into the plan's
   `**Gherkin persistence**:` metadata line and echo the recorded decision in the
   run output. The line records the destination **directory only** — the
   export script appends `<plan-slug>/` itself, so a `y` answer records `features`
   (files land in `features/<plan-slug>/`), never `features/<plan-slug>/`
   verbatim (that would double-nest). Echo example:
   `Recorded Gherkin persistence: features (files land in features/<plan-slug>/)`.
