#!/usr/bin/env python3
"""Python port of hooks/eval-compliance-check.sh (#599 / #572 Phase 3).

Claude Code PostToolUse hook. Fires after Write or Edit on any file. Runs
structural checks on agent/skill files and emits targeted doc-sync reminders
for config and general repo changes.

Contract (docs/python-hook-contract.md):
    Input : PostToolUse JSON on stdin with tool_input.file_path
    Output: advisory feedback on stdout (shown to Claude)
    Exit  : 0 always (advisory, never blocks)

Stdlib-only (json/pathlib/re/sys). Python 3.8+. See ADR 0014.

Refs: #572 (bash → Python migration epic).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Set


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def _load_input(raw: str) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _classify(file_path: str) -> str:
    """Mirror the .sh's `case` block. Order matches the .sh so the same
    file returns the same category on both sides."""
    if re.search(r"/agents/[^/]+\.md$", file_path):
        return "agent"
    if re.search(r"/skills/[^/]+/SKILL\.md$", file_path):
        return "skill"
    # Config: /.claude/hooks/*.sh, /.claude/settings.json, /CLAUDE.md
    if re.search(r"/\.claude/hooks/[^/]+\.sh$", file_path):
        return "config"
    if re.search(r"/\.claude/settings\.json$", file_path):
        return "config"
    if re.search(r"/CLAUDE\.md$", file_path):
        return "config"
    return "other"


def _grep_i_matches(content: str, pattern: str) -> bool:
    """Emulate `grep -qiE PATTERN` — case-insensitive extended regex."""
    return re.search(pattern, content, re.IGNORECASE) is not None


def _grep_matches(content: str, pattern: str) -> bool:
    """Emulate `grep -qE PATTERN` — case-sensitive extended regex."""
    return re.search(pattern, content) is not None


def _split_frontmatter(content: str) -> "tuple[str, str]":
    """Split a SKILL.md file into (frontmatter, body). If the file has no
    `---`-delimited frontmatter block, frontmatter is '' and body is the
    whole content."""
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            return content[3:end], content[end + 4 :]
    return "", content


def _is_user_invocable(frontmatter: str) -> bool:
    """True when the skill's frontmatter declares `user-invocable: true`
    (i.e. it's a slash command, not a purely agent-loaded knowledge skill)."""
    return (
        re.search(
            r"^user-invocable:\s*true\s*$", frontmatter, re.MULTILINE | re.IGNORECASE
        )
        is not None
    )


def _project_root(payload: dict) -> Path:
    """Resolve the project root the same way for every hook that needs one
    (docs/python-hook-contract.md § Environment variables): prefer
    ``CLAUDE_PROJECT_DIR``, fall back to the stdin payload's ``cwd``, then
    ``Path.cwd()``. Never raises."""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    return Path.cwd()


def _fixtured_agents(project_root: Path) -> Set[str]:
    """Scan ``evals/expected/*.json`` for ``applicableAgents`` (#860).

    Returns the empty set when ``evals/expected/`` does not exist — the
    normal shape for a cache-only plugin install (no ``evals/`` dir ships)
    — so the EVAL REQUIRED advisory below silently degrades to nothing
    rather than erroring."""
    expected_dir = project_root / "evals" / "expected"
    if not expected_dir.is_dir():
        return set()

    agents: Set[str] = set()
    for fixture_file in expected_dir.glob("*.json"):
        try:
            data = json.loads(fixture_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        applicable = data.get("applicableAgents")
        if isinstance(applicable, list):
            for entry in applicable:
                if isinstance(entry, str):
                    agents.add(entry)
    return agents


def _agent_checks(
    content: str,
    agent_name: str,
    file_path: str,
    eval_required: bool = False,
) -> str:
    """Return the full stdout block for an agent-file update.

    Order of checks matches the .sh; the FAILS and WARNS strings accumulate
    in appearance order and are emitted after the leading blank line.
    """
    fails: List[str] = []
    warnings: List[str] = []

    def fail(msg: str) -> None:
        fails.append(f"  FAIL: {msg}\n")

    def warn(msg: str) -> None:
        warnings.append(f"  WARN: {msg}\n")

    # 1. Structured output format (FAIL)
    if not _grep_i_matches(
        content,
        r"output.*json|json.*output|status.*pass.*warn.*fail",
    ):
        fail(
            f"{agent_name}: Missing structured output format "
            f"(must include status/issues/summary JSON schema)."
        )

    # 2. Severity definitions (FAIL)
    if not _grep_i_matches(
        content,
        r"severity.*error.*warning|error.*warning.*suggestion",
    ):
        fail(
            f"{agent_name}: Missing severity definitions "
            f"(must define error/warning/suggestion)."
        )

    # 3. Detection rules (WARN)
    if not _grep_i_matches(content, r"## Detect|## Check|## Rules"):
        warn(f"{agent_name}: Missing detection rules section.")

    # 4. Scope boundaries (WARN)
    if not _grep_i_matches(content, r"## Ignore|handled by other"):
        warn(
            f"{agent_name}: Missing scope boundaries (what does this agent NOT check?)."
        )

    # 5. Self-describing (FAIL)
    if _grep_i_matches(content, r"config.*json|review-config|config/"):
        fail(
            f"{agent_name}: References external config file. "
            f"Agents must be self-describing — declare thresholds, "
            f"file scope, and defaults inline."
        )

    # 7. Skip support (WARN)
    if not _grep_i_matches(content, r"## Skip"):
        warn(
            f"{agent_name}: Missing ## Skip section "
            f"(must define when agent is inapplicable)."
        )

    # 8. Model tier (WARN)
    if not _grep_i_matches(content, r"model tier:\s*(small|mid|frontier)"):
        warn(
            f"{agent_name}: Missing 'Model tier' field "
            f"(must be small, mid, or frontier)."
        )

    # 9. Context needs (WARN)
    if not _grep_i_matches(
        content,
        r"context needs:\s*(diff-only|full-file|project-structure)",
    ):
        warn(
            f"{agent_name}: Missing 'Context needs' field "
            f"(must be diff-only, full-file, or project-structure)."
        )

    # 6. File scope for language-specific agents (WARN)
    # The .sh's outer pattern is `javascript|typescript|python|...`.
    # NOTE: the .sh literal `javascript\|typescript\|python\|...` looks like
    # it intends BRE-style alternation but grep -E treats backslash-pipe as
    # a literal pipe. We match the exact bytes the .sh checks — the same
    # pattern with escaped pipes as literal chars.
    if _grep_i_matches(
        content,
        r"javascript\\\|typescript\\\|python\\\|ruby\\\|go\\\|rust\\\|java",
    ):
        if not _grep_i_matches(
            content,
            r"scope:|\.js\b|\.ts\b|\.py\b|\.rb\b|\.go\b|\.rs\b|\.java\b|files only",
        ):
            warn(
                f"{agent_name}: Mentions a language but doesn't declare "
                f"file scope (e.g., 'Scope: *.js, *.ts files only')."
            )

    parts: List[str] = ["\n"]
    if fails:
        parts.append("".join(fails))
    if warnings:
        parts.append("".join(warnings))
    parts.append("\n")
    parts.append(f"  Agent file changed: {agent_name}\n")
    parts.append(f"  ACTION REQUIRED: Run /agent-audit {file_path}\n")
    if eval_required:
        parts.append(
            f"  EVAL REQUIRED: this agent has eval fixtures — run "
            f"/agent-eval --agent {agent_name} and record the result "
            f"before adopting this change.\n"
        )
    parts.append(
        "  DOC SYNC REQUIRED: Update .claude/CLAUDE.md and "
        "docs/agent_info.md to reflect any changes.\n"
    )
    parts.append(
        "  Invoke the tech-writer persona to review affected "
        "documentation before marking this task complete.\n"
    )
    return "".join(parts)


def _skill_checks(content: str, skill_name: str) -> str:
    fails: List[str] = []
    warnings: List[str] = []

    def fail(msg: str) -> None:
        fails.append(f"  FAIL: {msg}\n")

    def warn(msg: str) -> None:
        warnings.append(f"  WARN: {msg}\n")

    # 1. Role declaration (WARN)
    #
    # User-invocable skills (slash commands) are workflow initiators — they
    # need an explicit `Role:` line in the SKILL.md *body* (immediately after
    # the H1, matching /plan, /build, /code-review, /pr, /ship). A
    # frontmatter-only `role:` field is not sufficient for these: it's easy
    # to add without ever stating the orchestration-discipline contract the
    # body line carries (see agents/orchestrator.md). Agent-loaded,
    # non-user-invocable knowledge skills are exempt from the stricter body
    # check — a frontmatter `role:` (or nothing, for pure reference material)
    # is fine for those.
    frontmatter, body = _split_frontmatter(content)
    if _is_user_invocable(frontmatter):
        if not re.search(
            r"^Role:\s*(orchestrator|worker|implementation)\b",
            body,
            re.MULTILINE,
        ):
            warn(
                f"{skill_name}: Missing explicit 'Role:' line in the skill body "
                f"(user-invocable workflow skills must declare Role: orchestrator, "
                f"worker, or implementation right after the H1 — a frontmatter-only "
                f"`role:` field does not satisfy this)."
            )
    elif not _grep_i_matches(
        content,
        r"role:\s*(orchestrator|worker|implementation)",
    ):
        warn(
            f"{skill_name}: Missing 'Role:' declaration "
            f"(must be orchestrator, worker, or implementation)."
        )

    # 2. Constraints (WARN)
    if not _grep_i_matches(content, r"constraints"):
        warn(f"{skill_name}: Missing constraints section for role boundaries.")

    # 3. Conciseness (WARN)
    if not _grep_i_matches(content, r"be concise|concise"):
        warn(
            f"{skill_name}: Missing conciseness directive "
            f"(must instruct concise output to reduce token usage)."
        )

    # 4. Structured steps (FAIL) — case-sensitive
    if not _grep_matches(content, r"### [0-9]+\.|## Steps"):
        fail(f"{skill_name}: Missing numbered steps.")

    # 4b. Argument parsing (WARN)
    if not _grep_i_matches(content, r"argument|parse|args"):
        warn(f"{skill_name}: Missing argument parsing section.")

    # 5. Report section for review-related skills (WARN)
    if _grep_i_matches(content, r"review|audit|fix"):
        if not _grep_i_matches(content, r"report|summary|output"):
            warn(f"{skill_name}: Review-related skill missing report/summary section.")

    if not fails and not warnings:
        return ""

    parts: List[str] = ["\n"]
    if fails:
        parts.append("".join(fails))
    if warnings:
        parts.append("".join(warnings))
    parts.append("\n")
    parts.append("  Run /agent-audit for a full compliance report.\n")
    return "".join(parts)


def _config_notice(file_path: str) -> str:
    config_name = Path(file_path).name
    parts = [
        "\n",
        f"  Config file changed: {config_name}\n",
        "  DOC SYNC REQUIRED: Verify affected documentation is current:\n",
    ]
    # Match the .sh's `case "$FILE_PATH" in` selector.
    if re.search(r"/hooks/[^/]+\.sh$", file_path):
        parts.append("    - CLAUDE.md (hooks section)\n")
        parts.append("    - docs/agent-architecture.md (Governance section)\n")
    elif re.search(r"/settings\.json$", file_path):
        parts.append("    - CLAUDE.md (plugins/skills registry)\n")
        parts.append("    - docs/agent-architecture.md (Governance section)\n")
    elif re.search(r"/CLAUDE\.md$", file_path):
        parts.append("    - docs/ (any section that mirrors CLAUDE.md tables)\n")
    parts.append(
        "  Invoke the tech-writer persona to review before marking the task complete.\n"
    )
    return "".join(parts)


def _other_notice(file_path: str) -> Optional[str]:
    """Return the general-repo advisory, or None if the file matches a
    skip pattern (lock/memory/metrics/evals/logs/docs/README)."""
    # The .sh's case pattern uses `*lock*` etc. — matches ANY occurrence
    # of the substring in the path.
    skip_patterns = [
        r"lock",
        r"/memory/",
        r"/metrics/",
        r"/evals/",
        r"\.log$",
        r"/docs/[^/]+\.md$",
        r"/README",
    ]
    for pat in skip_patterns:
        if re.search(pat, file_path):
            return None

    changed_name = Path(file_path).name
    return (
        "\n"
        f"  File changed: {changed_name}\n"
        "  DOC SYNC CHECK: If this change affects observable behavior or "
        "architecture, update:\n"
        "    - docs/agent-architecture.md "
        "(system design or configuration changes)\n"
        "    - README.md            "
        "(top-level changes visible to new users)\n"
        "  Invoke the tech-writer persona to confirm docs are current "
        "before closing the task.\n"
    )


def main() -> int:
    raw = _read_stdin()
    payload = _load_input(raw)
    tool_input = (
        payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    )
    file_path = tool_input.get("file_path") or ""
    if not isinstance(file_path, str):
        file_path = ""

    file_type = _classify(file_path)
    if not Path(file_path).is_file():
        return 0

    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    if file_type == "agent":
        agent_name = Path(file_path).stem
        fixtured = _fixtured_agents(_project_root(payload))
        sys.stdout.write(
            _agent_checks(
                content, agent_name, file_path, eval_required=agent_name in fixtured
            )
        )
    elif file_type == "skill":
        skill_name = Path(file_path).stem
        block = _skill_checks(content, skill_name)
        if block:
            sys.stdout.write(block)
    elif file_type == "config":
        sys.stdout.write(_config_notice(file_path))
    else:  # other
        notice = _other_notice(file_path)
        if notice is not None:
            sys.stdout.write(notice)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
