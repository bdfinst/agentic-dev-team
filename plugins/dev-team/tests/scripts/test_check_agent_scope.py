"""Tests for scripts/check_agent_scope.py.

``Scope:`` is a body-level declaration, not frontmatter (issue #1333).
"""

import sys
import textwrap
from pathlib import Path

# Make the scripts directory importable
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_agent_scope import (
    declares_scope,
    has_frontmatter,
    main,
    strip_frontmatter,
)

# ---------------------------------------------------------------------------
# declares_scope / strip_frontmatter unit tests
# ---------------------------------------------------------------------------

def test_declares_scope_scalar():
    text = textwrap.dedent("""\
        ---
        name: my-agent
        ---
        # Body
        Scope: always
    """)
    body = strip_frontmatter(text)
    assert declares_scope(body)


def test_declares_scope_list():
    text = textwrap.dedent("""\
        ---
        name: svelte-review
        ---
        # Body
        Scope:
        - **/*.svelte
        - **/*.svelte.ts
    """)
    body = strip_frontmatter(text)
    assert declares_scope(body)


def test_no_frontmatter_is_detected():
    text = "# Just a plain file\nno frontmatter here."
    assert not has_frontmatter(text)


def test_declares_scope_false_when_missing():
    text = textwrap.dedent("""\
        ---
        name: my-agent
        ---
        # Body
        No scope line here.
    """)
    body = strip_frontmatter(text)
    assert not declares_scope(body)


# ---------------------------------------------------------------------------
# main() integration tests using tmp directories
# ---------------------------------------------------------------------------

def _write_agent(directory: Path, name: str, content: str) -> None:
    (directory / f"{name}.md").write_text(content)


def test_main_all_agents_have_scope(tmp_path, capsys):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "doc-review", textwrap.dedent("""\
        ---
        name: doc-review
        description: Docs
        effort: medium
        ---
        # Doc Review
        Scope: always
    """))
    _write_agent(agents_dir, "svelte-review", textwrap.dedent("""\
        ---
        name: svelte-review
        description: Svelte
        effort: low
        ---
        # Svelte Review
        Scope:
        - **/*.svelte
    """))
    rc = _call_main(agents_dir)
    assert rc == 0


def test_main_missing_scope_fails(tmp_path, capsys):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "missing-scope-review", textwrap.dedent("""\
        ---
        name: missing-scope-review
        description: Something
        effort: medium
        ---
        # Review
    """))
    rc = _call_main(agents_dir)
    assert rc == 1
    captured = capsys.readouterr()
    assert "missing-scope-review" in captured.out


def test_main_non_review_agent_skipped(tmp_path, capsys):
    """Non-review agents listed in NON_REVIEW_AGENTS should not cause failure."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    # orchestrator has no Scope: declaration — should be skipped
    _write_agent(agents_dir, "orchestrator", textwrap.dedent("""\
        ---
        name: orchestrator
        description: Routes tasks
        effort: high
        ---
        # Orchestrator
    """))
    rc = _call_main(agents_dir)
    assert rc == 0


def _call_main(agents_dir: Path) -> int:
    """Call main() with --agents-dir override via sys.argv."""
    old_argv = sys.argv[:]
    sys.argv = ["check_agent_scope.py", "--agents-dir", str(agents_dir)]
    try:
        return main()
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    finally:
        sys.argv = old_argv
