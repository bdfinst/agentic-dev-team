"""Pytest tests for the `Role:` declaration check in hooks/eval_compliance_check.py
(issue #884).

Regression fixture: before this fix, a user-invocable skill with only a
frontmatter `role: worker` field (no explicit `Role:` line in the SKILL.md
body) satisfied the old regex — `role:\\s*(orchestrator|worker|implementation)`
matched anywhere in the file, including frontmatter — so /specs and
/design-doc silently passed with no visible role declaration in their bodies.
The tightened check requires the explicit body line for user-invocable
skills; frontmatter-only `role:` is exempt only for non-user-invocable,
agent-loaded knowledge skills.

Drives main() via subprocess with representative PostToolUse JSON payloads,
matching the pattern used by tests/hooks/test_js_fp_review.py. The hook is
advisory-only (always exits 0).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "eval_compliance_check.py"


def _run(file_path: Path) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    payload = {"tool_input": {"file_path": str(file_path)}}
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _write_skill(tmp_path: Path, name: str, body: str) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(body, encoding="utf-8")
    return skill_file


# Minimal skill bodies share the mechanical scaffolding (numbered steps,
# constraints, concise directive) so only the Role: declaration varies —
# the other WARN/FAIL checks are covered by other test files.
_SCAFFOLD = """
## Constraints

- Be concise.

## Steps

### 1. Do the thing
"""


def test_user_invocable_skill_with_only_frontmatter_role_is_flagged(
    tmp_path: Path,
) -> None:
    """The exact bug shape: pre-fix /specs and /design-doc — a user-invocable
    skill declares `role: worker` in frontmatter but has no body `Role:` line.
    This must now be WARNed."""
    content = f"""---
name: fixture-pipeline-initiator
description: A fixture workflow skill with no explicit Role line.
role: worker
user-invocable: true
---

# Fixture Pipeline Initiator
{_SCAFFOLD}
"""
    skill_file = _write_skill(tmp_path, "fixture-pipeline-initiator", content)
    result = _run(skill_file)
    assert result.returncode == 0
    out = result.stdout.decode()
    assert "Missing explicit 'Role:' line in the skill body" in out


def test_user_invocable_skill_with_explicit_body_role_line_passes(
    tmp_path: Path,
) -> None:
    """Same fixture, fixed: an explicit body `Role:` line silences the WARN."""
    content = f"""---
name: fixture-pipeline-initiator
description: A fixture workflow skill with an explicit Role line.
role: worker
user-invocable: true
---

# Fixture Pipeline Initiator

Role: worker. This command does the fixture's work directly.
{_SCAFFOLD}
"""
    skill_file = _write_skill(tmp_path, "fixture-pipeline-initiator", content)
    result = _run(skill_file)
    assert result.returncode == 0
    out = result.stdout.decode()
    assert "Missing explicit 'Role:' line in the skill body" not in out
    assert "Missing 'Role:' declaration" not in out


def test_non_user_invocable_knowledge_skill_exempt_from_body_line(
    tmp_path: Path,
) -> None:
    """Agent-loaded, non-user-invocable knowledge skills are exempt from the
    stricter body-line requirement — a frontmatter `role:` field is enough."""
    content = f"""---
name: fixture-knowledge-skill
description: A fixture agent-loaded knowledge skill.
role: worker
---

# Fixture Knowledge Skill
{_SCAFFOLD}
"""
    skill_file = _write_skill(tmp_path, "fixture-knowledge-skill", content)
    result = _run(skill_file)
    assert result.returncode == 0
    out = result.stdout.decode()
    assert "Missing explicit 'Role:' line in the skill body" not in out
    assert "Missing 'Role:' declaration" not in out


def test_non_user_invocable_skill_with_no_role_anywhere_still_flagged(
    tmp_path: Path,
) -> None:
    """The original, lenient check is preserved for non-user-invocable
    skills: a role declared nowhere at all is still WARNed."""
    content = f"""---
name: fixture-knowledge-skill-no-role
description: A fixture agent-loaded knowledge skill missing role entirely.
---

# Fixture Knowledge Skill No Role
{_SCAFFOLD}
"""
    skill_file = _write_skill(tmp_path, "fixture-knowledge-skill-no-role", content)
    result = _run(skill_file)
    assert result.returncode == 0
    out = result.stdout.decode()
    assert "Missing 'Role:' declaration" in out
