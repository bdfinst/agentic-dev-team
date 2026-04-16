# Installing Agentic Dev Team for Codex CLI

## Prerequisites

- [Codex CLI](https://developers.openai.com/codex) installed
- Git

## Setup

### 1. Clone or download the plugin

```bash
git clone https://github.com/bdfinst/agentic-dev-team.git
cd agentic-dev-team/plugins/agentic-dev-team
```

### 2. Set up skills discovery

Codex scans `.agents/skills/` for SKILL.md files. Create a symlink from your project to the plugin's skills:

```bash
# From your project root:
mkdir -p .agents
ln -s /path/to/agentic-dev-team/plugins/agentic-dev-team/skills .agents/skills
```

Or copy the skills directory if symlinks aren't practical.

### 3. Copy configuration files

```bash
# From your project root:
cp /path/to/agentic-dev-team/plugins/agentic-dev-team/AGENTS.md ./AGENTS.md
cp -r /path/to/agentic-dev-team/plugins/agentic-dev-team/.codex ./.codex
```

### 4. Verify

Start Codex CLI in your project. The skills should be discoverable:
- Use `$` mention syntax to invoke skills explicitly
- Skills with matching descriptions activate implicitly

## Capability Limitations

See the "Capability Limitations on Codex" section in AGENTS.md for details on what features require Claude Code for full functionality.

## Updating

Pull the latest plugin version and re-copy AGENTS.md and .codex/ files:

```bash
cd /path/to/agentic-dev-team
git pull
cp plugins/agentic-dev-team/AGENTS.md /path/to/your/project/AGENTS.md
cp -r plugins/agentic-dev-team/.codex /path/to/your/project/.codex
```
