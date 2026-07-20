# Contributing

How to develop, test, and release the `dev-team`, `security-assessment`, and `marketplace-dev` plugins. To *use* the plugins, see the [README](README.md) and the [Getting Started](GETTING-STARTED.md) tutorial.

## Repository layout

```text
.claude-plugin/marketplace.json    # marketplace catalog (the published plugin list)
plugins/dev-team/                  # the dev-team plugin source
plugins/security-assessment/       # the security companion plugin
plugins/marketplace-dev/           # the plugin-author's toolkit (scaffold/audit/agent authoring)
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

The agent-authoring commands — `/agent-add`, `/agent-create`, `/agent-remove` — and the `agent-skill-authoring` skill ship in the **`marketplace-dev`** plugin, not `dev-team`. Install `marketplace-dev` (see [Getting Started](GETTING-STARTED.md#install-marketplace-dev-optional)) before using them.

Scaffold a new agent (review or team) with the authoring command:

```text
/agent-add <description or URL to a coding standard>
```

`/agent-add` scaffolds the file, checks for scope overlap with existing agents, runs `/agent-audit`, creates eval fixtures, and registers the agent. `/agent-create` builds one from scratch and `/agent-remove` deletes an agent and its registrations. For the templates, schema, and registration steps, see:

- [Agents](plugins/dev-team/docs/agent_info.md) — team-agent and review-agent templates; add, remove, or customize agents
- [Skills & Commands](plugins/dev-team/docs/skills.md) — skill template; add a knowledge or user-invocable (slash-command) skill
- the `agent-skill-authoring` skill (marketplace-dev) — conventions, anti-patterns, and the agent-vs-skill philosophy

Every new or changed agent/skill/hook must pass `/agent-audit` (which ships in `dev-team`).

## Documentation diagrams

The docs use three diagram formats, each for a distinct purpose — match the convention when adding or editing a diagram:

- **Mermaid** (` ```mermaid ` fences) — the default for flow, sequence, and architecture diagrams authored inline. It is text-based (diffs cleanly), renders on GitHub natively, and renders on the [docs site](https://devteam.bryanfinster.com/) (Material loads Mermaid.js via the `pymdownx.superfences` custom fence in `mkdocs.yml`). Reuse the shared `%%{init ...}%%` theme block from an existing diagram (e.g. `plugins/dev-team/docs/model-routing.md`) so diagrams look consistent.
- **SVG** (`plugins/dev-team/docs/diagrams/*.svg`) — reserved for the polished, hand-tuned architecture diagrams that are laid out deliberately and tuned for dark mode. Don't auto-convert these to Mermaid; edit the SVG.
- **ASCII** (plain ` ``` ` fences) — only for directory/file trees and short inline command flows, never for boxes-and-arrows diagrams (use Mermaid for those).

## Releasing

Releases are managed by [release-please](https://github.com/googleapis/release-please): push [conventional commits](https://www.conventionalcommits.org/) to `main` and merge the release PR it opens. The full rules — the version-bump mapping, why every commit that lands on `main` must be conventional under rebase-merge, and how to recover a missed release with a `Release-As:` footer — are in [`CLAUDE.md`](CLAUDE.md#releasing).
