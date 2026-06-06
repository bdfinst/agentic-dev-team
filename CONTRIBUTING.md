# Contributing

How to develop, test, and release the `dev-team` and `security-assessment` plugins. To *use* the plugins, see the [README](README.md) and the [Getting Started](GETTING-STARTED.md) tutorial.

## Repository layout

```text
.claude-plugin/marketplace.json    # marketplace catalog (the published plugin list)
plugins/dev-team/                  # the dev-team plugin source
plugins/security-assessment/       # the security companion plugin
docs/                              # repo-level documentation
evals/                            # eval fixtures and harnesses (not shipped)
```

Edit plugin components directly under `plugins/<plugin>/` (agents, skills, hooks, knowledge, templates, docs). See [`plugins/dev-team/CLAUDE.md`](plugins/dev-team/CLAUDE.md) for the orchestration pipeline.

## Local development

Two ways to run the plugins from your working tree.

### Quick test install (committed state)

Register the local checkout as a marketplace, then install from it into a test project:

```bash
claude plugin marketplace add /path/to/agentic-dev-team
claude plugin install --scope project dev-team@bfinster
claude plugin install --scope project security-assessment@bfinster
```

Because the marketplace entries use a `git-subdir` source, this serves each plugin from its git ref — good for smoke-testing a release, but it does **not** reflect uncommitted edits.

### Live local dev (uncommitted edits via symlinks)

To have Claude Code pick up local edits immediately, three paths must point at your local repo (`/path/to/agentic-dev-team`). Claude Code reads plugin commands from the marketplace directory at startup, so a stale clone there will shadow your changes:

1. `~/.claude/plugins/installed_plugins.json` — set the plugin's `installPath` to the local repo.
2. `~/.claude/plugins/known_marketplaces.json` — set `installLocation` to the local repo.
3. `~/.claude/plugins/marketplaces/<marketplace-dir>` — replace the cloned directory with a symlink to the local repo:

   ```bash
   rm -rf ~/.claude/plugins/marketplaces/agentic-dev-team
   ln -s /path/to/agentic-dev-team ~/.claude/plugins/marketplaces/agentic-dev-team
   ```

Also delete `~/.claude/plugins/cache/agentic-dev-team/` — it can regenerate from stale data. Restart Claude Code after changing these paths.

> Skipping any of the three leaves a stale clone that silently shadows your edits — the failure mode is "my change isn't taking effect." If in doubt, check all three before debugging the plugin itself.

## Testing

### Agents and hooks (dev-team)

```text
/agent-eval                                              # full eval suite
/agent-eval plugins/dev-team/agents/naming-review.md     # one agent
/agent-audit                                             # structural compliance
```

Run `/agent-audit` after any agent, skill, or hook change. Run `/agent-eval` after changing a review agent to check detection accuracy against the eval corpus.

### Comparative-testing harness (security-assessment)

Regression-test the `/security-assessment` pipeline against a seeded fixture and reference baseline:

```bash
python3 evals/comparative/score.py \
  --reference evals/comparative/reference-baseline/2026-04-21 \
  --ours memory
```

See [comparative testing](plugins/security-assessment/docs/comparative-testing.md) for the scoring methodology.

## Adding agents and skills

Scaffold a new agent (review or team) with the authoring command:

```text
/agent-add <description or URL to a coding standard>
```

`/agent-add` scaffolds the file, checks for scope overlap with existing agents, runs `/agent-audit`, creates eval fixtures, and registers the agent. For the templates, schema, and registration steps, see:

- [Agents](plugins/dev-team/docs/agent_info.md) — team-agent and review-agent templates; add, remove, or customize agents
- [Skills & Commands](plugins/dev-team/docs/skills.md) — skill template; add a knowledge or user-invocable (slash-command) skill
- the `agent-skill-authoring` skill — conventions, anti-patterns, and the agent-vs-skill philosophy

Every new or changed agent/skill/hook must pass `/agent-audit`.

## Releasing

Releases are managed by [release-please](https://github.com/googleapis/release-please). Push [conventional commits](https://www.conventionalcommits.org/) to `main`:

- `feat:` → minor version bump
- `fix:` → patch version bump
- `feat!:` or `BREAKING CHANGE:` → major version bump

A release PR is opened automatically; merging it creates a GitHub Release with a version tag. The marketplace catalog serves only tagged releases.
