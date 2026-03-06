# Setup

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- `jq` installed (required by PostToolUse hooks for JSON parsing)
  - macOS: `brew install jq`
  - Linux: `apt install jq` or `yum install jq`

## Install via Plugin (recommended)

1. Add this repo as a marketplace source:

   ```bash
   claude plugin marketplace add <your-org>/agentic-dev-team
   ```

2. Install the plugin (project-scoped or user-scoped):

   ```bash
   # project-scoped — adds to this project only, registered in settings.json
   claude plugin install agentic-dev-team@<your-org>/agentic-dev-team

   # user-scoped — available in all your projects
   claude plugin install --scope user agentic-dev-team@<your-org>/agentic-dev-team
   ```

3. Run the prerequisite check:

   ```bash
   ./install.sh
   ```

4. Start Claude Code:

   ```bash
   claude
   ```

Claude automatically loads `CLAUDE.md` on startup. Agent and skill files are loaded on demand as tasks require them.

## Beads (recommended)

Beads is a git-backed issue tracker for AI agents. Agents query `bd ready --json` at session start for persistent, structured task memory. Without Beads, agents fall back to `memory/` progress files.

Install once, system-wide:

```bash
npm install -g @beads/bd
# or: brew install beads
```

Initialize in your project:

```bash
bd init
git add .beads && git commit -m "Initialize Beads task tracker"
```

Add the session-start hook to your global `~/.claude/CLAUDE.md`:

```markdown
## Session Start
At the beginning of every session, run `bd prime` to load Beads context before any other work.
```

## Manual Install (alternative)

If you prefer not to use the plugin system, copy the plugin directories into your project:

```bash
git clone <repo-url> agentic-dev-team

cp -r agentic-dev-team/agents   /path/to/your-project/.claude/agents
cp -r agentic-dev-team/skills   /path/to/your-project/.claude/skills
cp -r agentic-dev-team/commands /path/to/your-project/.claude/commands
cp -r agentic-dev-team/hooks    /path/to/your-project/.claude/hooks
cp    agentic-dev-team/CLAUDE.md /path/to/your-project/.claude/CLAUDE.md
```

Then register the hooks in your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{ "type": "command", "command": "bash .claude/hooks/pre-tool-guard.sh" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/js-fp-review.sh" },
          { "type": "command", "command": "bash .claude/hooks/token-efficiency-review.sh" },
          { "type": "command", "command": "bash .claude/hooks/eval-compliance-check.sh" }
        ]
      }
    ]
  }
}
```

### Selective installation (review agents only)

If you only want the code review pipeline without the full team persona system:

```bash
cp -r agentic-dev-team/agents/*-review.md /path/to/your-project/.claude/agents/
cp -r agentic-dev-team/skills              /path/to/your-project/.claude/skills/
cp    agentic-dev-team/commands/code-review.md     /path/to/your-project/.claude/commands/
cp    agentic-dev-team/commands/review-agent.md    /path/to/your-project/.claude/commands/
cp    agentic-dev-team/commands/apply-fixes.md     /path/to/your-project/.claude/commands/
```

Then add the Review Agents registry table from `agentic-dev-team/CLAUDE.md` into your project's `CLAUDE.md`.

### Merging with an existing `.claude/` directory

If your project already has a `.claude/` configuration, merge selectively:

```bash
cp -r agentic-dev-team/agents   /path/to/your-project/.claude/agents/
cp -r agentic-dev-team/skills   /path/to/your-project/.claude/skills/
cp -r agentic-dev-team/commands /path/to/your-project/.claude/commands/
```

Manually copy the agent registry tables from `agentic-dev-team/CLAUDE.md` into your project's `CLAUDE.md`. Agents not listed in `CLAUDE.md` will not be routed to by the Orchestrator.

For adding individual agents from this repo or other repositories, see [Agents — Custom and Cross-Repo](agent_info.md#add-a-project-specific-custom-agent).

## Hooks

One PreToolUse hook runs before every file write or edit:

- `pre-tool-guard.sh` — blocks writes to sensitive paths (credentials, keys, secrets); warns on writes to protected config files. Configured via `hooks/guards.json`.

Three PostToolUse hooks run after every file write or edit:

- `js-fp-review.sh` — warns on array mutations and impure patterns in JS/TS files
- `token-efficiency-review.sh` — warns when files exceed recommended size limits
- `eval-compliance-check.sh` — warns when agent or command files are missing required structural elements

PostToolUse hooks are advisory — they never block writes. The PreToolUse guard can block writes to protected paths (exit 2).

## Verify

After starting Claude Code, the Orchestrator pipeline is active. Submit any natural language request to confirm the system is working:

```text
> What agents are available on this team?
```
