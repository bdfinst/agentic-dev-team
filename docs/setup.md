# Setup

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated

## Install

1. Clone the repository:

   ```bash
   git clone <repo-url> agentic-scrum-team
   ```

2. Copy `.claude/` into your target project:

   ```bash
   cp -r agentic-scrum-team/.claude/ /path/to/your-project/.claude/
   ```

3. Start Claude Code:

   ```bash
   cd /path/to/your-project
   claude
   ```

Claude automatically loads `CLAUDE.md` on startup. Agent and skill files are loaded on demand as tasks require them.

## Verify

After starting Claude Code, the Scrum Master orchestration pipeline is active. Submit any natural language request to confirm the system is working:

```text
> What agents are available on this team?
```
