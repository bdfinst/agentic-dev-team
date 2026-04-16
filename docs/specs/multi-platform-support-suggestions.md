# Multi-Platform Support: Suggestions (Research Only)

**Date**: 2026-04-16
**Source**: Competitive analysis against [obra/superpowers](https://github.com/obra/superpowers) which supports 6 platforms.
**Status**: Research document — no implementation planned without further decision.

## Current State

A platform dependency audit found that **97.4% of plugin files (151 of ~155) have Claude Code-specific dependencies**. Only 4 knowledge files are fully portable as pure markdown:

- `knowledge/review-rubric.md`
- `knowledge/owasp-detection.md`
- `knowledge/domain-modeling.md`
- `knowledge/architecture-assessment.md`

### Claude Code Features We Depend On

| Feature | Files affected | Portability barrier |
|---------|---------------|-------------------|
| **Agent tool** (subagent dispatch with model override, `isolation: "worktree"`) | Orchestrator, build, triage commands | No equivalent in Cursor, Codex, Gemini CLI. This is the hardest barrier. |
| **Hooks** (PreToolUse, PostToolUse) | 8 bash scripts + settings.json | No hook system in other platforms. Would need middleware. |
| **`allowed-tools:` frontmatter** (scoped tool permissions) | All 29 command files | Claude Code security feature with no cross-platform equivalent. |
| **`tools:` frontmatter** in agents | All 30 agent files | Tool names (Read, Write, Edit, Glob, Grep, Bash, Agent) are Claude Code-specific. |
| **`model:` frontmatter** in agents | All 30 agent files + 9 templates | Model names (haiku, sonnet, opus) map to Claude models. Other platforms may use different models. |
| **Plugin manifest** (`.claude-plugin/plugin.json`) | 1 file | Different format per platform. |
| **Skill frontmatter** (`user-invocable`, `role`) | All 32 skill files | Claude Code skill discovery mechanism. |

## How Superpowers Does It

superpowers supports 6 platforms with these strategies:

1. **Platform-specific manifests**: `.claude-plugin/plugin.json`, `.cursor-plugin/`, `.codex/`, `.opencode/`, `gemini-extension.json`, `AGENTS.md` (Copilot). Each manifest points to the same skill files.

2. **SessionStart hook with platform detection**: A single hook fires on session start, detects which platform is running, and injects skill awareness. The hook has platform-specific variants (`hooks.json` for Claude Code, `hooks-cursor.json` for Cursor).

3. **Skills as the portable unit**: Skills are plain markdown with YAML frontmatter. The frontmatter is minimal (name, description). No `tools:`, `model:`, or `allowed-tools:` — those concepts don't exist in superpowers' skills.

4. **Graceful degradation**: The `executing-plans` skill is a fallback for platforms without subagent support. Instead of dispatching parallel subagents, the agent executes plan steps inline. superpowers explicitly states: "Superpowers performs significantly better with subagent access."

5. **Single agent, not a fleet**: superpowers has 1 agent (code-reviewer). Our 30 agents and 19 review agents are a much larger portability surface.

## Portability Assessment

### What is portable today (no changes needed)

| Layer | Files | Notes |
|-------|-------|-------|
| Knowledge files (4) | review-rubric, owasp-detection, domain-modeling, architecture-assessment | Pure markdown reference. Portable as-is. |
| Skill content (32) | All SKILL.md files | The *content* of skills (patterns, guidelines, procedures) is platform-agnostic markdown. The *frontmatter* is Claude Code-specific. |
| Prompt templates (4+) | plan-review-*.md, future implementer/spec/quality | Pure prompt text. Portable as-is. |
| Knowledge file content (2) | agent-registry, review-template | Content is portable but references Claude Code tool names. |

### What requires an adapter layer

| Layer | Files | Adaptation needed |
|-------|-------|-----------------|
| Agent files (30) | All agents | Strip `tools:` and `model:` frontmatter for other platforms, or map to platform equivalents. |
| Command files (29) | All commands | Strip `allowed-tools:` for platforms without scoped permissions. Degrade gracefully. |
| Skill frontmatter (32) | All skills | Simplify to name + description only for non-Claude platforms. |
| Plugin manifest (1) | `.claude-plugin/plugin.json` | Create parallel manifests for each platform. |

### What cannot be ported without redesign

| Feature | Why | Impact |
|---------|-----|--------|
| **Multi-agent orchestration** (Agent tool + model routing) | Other platforms have no equivalent to dispatching subagents with model override and worktree isolation. | The entire orchestrator workflow (Research → Plan → Implement with parallel subagents, inline review checkpoints, model-routed review agents) would need a fallback. |
| **Hook-based guards** (8 scripts) | Hooks are a Claude Code-specific runtime feature. Pre-tool guards, TDD enforcement, and real-time review checks have no equivalent elsewhere. | Safety rails and automated quality checks would be manual-only. |
| **Scoped tool permissions** | `allowed-tools:` restricts what each command can do. Other platforms don't have this security model. | Commands would have full tool access on other platforms — less secure. |

## Suggested Approach

### Option 1: Minimal adapter (Low effort, limited reach)

Add platform manifests that point to the existing skills and knowledge files. Accept that orchestration, hooks, and review agents don't work on other platforms. The plugin becomes a "knowledge library" on non-Claude platforms.

**Effort**: Small (create manifest files + SessionStart hook per platform)
**Value**: Low (most of the plugin's value IS the orchestration)

### Option 2: Graceful degradation (Medium effort, moderate reach)

Like superpowers' approach: add an `executing-plans` fallback mode where the agent works inline instead of dispatching subagents. Hooks degrade to "manual checklist" instructions. Review agents degrade to a single inline review pass.

**What this looks like**:
1. Add platform manifests (`.cursor-plugin/`, `.codex/`, etc.)
2. Create a SessionStart hook that detects platform and sets a `PLATFORM` variable
3. Create a `skills/inline-execution/SKILL.md` fallback for platforms without Agent tool
4. Modify the orchestrator to check platform and switch between multi-agent and inline modes
5. Convert hook-based guards to skill-based checklists (manual enforcement)
6. Strip `tools:`, `model:`, `allowed-tools:` from agent/command files on other platforms (or make them optional with sensible defaults)

**Effort**: Large
**Value**: Moderate (the inline fallback is significantly less capable than the full orchestration)
**Risk**: Maintaining two execution paths (multi-agent + inline) doubles the testing and maintenance burden. Every new feature needs both paths.

### Option 3: Platform abstraction layer (High effort, full reach)

Create an abstraction layer that maps platform-specific capabilities to a common interface. Agent dispatch, tool access, and hooks are abstracted behind platform adapters.

**Effort**: XL
**Value**: High (full functionality on all platforms)
**Risk**: Over-engineering. The abstraction layer becomes its own maintenance burden. Claude Code is our primary platform — optimizing for 5 other platforms that may never have equivalent features is speculative.

## Recommendation

**Do not pursue multi-platform support now.** The cost-benefit analysis doesn't justify it:

- 97% of our files have Claude Code dependencies
- Our core value proposition (multi-agent orchestration, review agent fleet, hook-based guards) depends on Claude Code features that other platforms don't have
- superpowers can be multi-platform because it's a workflow discipline tool (14 skills, 1 agent). We're an orchestration platform (30 agents, 29 commands, 8 hooks). The portability surface is fundamentally different.

**Revisit when**:
1. Other platforms add subagent dispatch (Cursor is most likely to get this)
2. A significant user base requests it
3. A platform-agnostic agent dispatch standard emerges

**Quick win available now**: Extract the 4 portable knowledge files + skill content (without frontmatter) into a standalone "reference library" that other tools can consume. This is useful for teams that want our detection patterns and rubrics without the orchestration. Effort: Small.

## Per-Platform Effort Estimates

| Platform | Effort | Biggest risk |
|----------|--------|-------------|
| **Cursor** | L | No subagent dispatch; hooks require cursor-specific format; closest to Claude Code in capability |
| **Codex (OpenAI)** | XL | Fundamentally different agent model; AGENTS.md format; no hooks; different model names |
| **OpenCode** | L | Smaller platform; limited docs on plugin capabilities |
| **Gemini CLI** | XL | Different model family entirely (Gemini not Claude); extension format; no subagent dispatch |
| **GitHub Copilot CLI** | XL | Least mature agent platform; minimal plugin system |
