"""Tests for scripts/check_agent_scope.py."""

import sys
import textwrap
from pathlib import Path

import pytest

# Make the scripts directory importable
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_agent_scope import main, parse_frontmatter  # noqa: E402


# ---------------------------------------------------------------------------
# parse_frontmatter unit tests
# ---------------------------------------------------------------------------

def test_parse_frontmatter_scalar():
    text = textwrap.dedent("""\
        ---
        name: my-agent
        scope: always
        effort: medium
        ---
        # Body
    """)
    fm = parse_frontmatter(text)
    assert fm["name"] == "my-agent"
    assert fm["scope"] == "always"
    assert fm["effort"] == "medium"


def test_parse_frontmatter_list():
    text = textwrap.dedent("""\
        ---
        name: svelte-review
        scope:
          - **/*.svelte
          - **/*.svelte.ts
        ---
        # Body
    """)
    fm = parse_frontmatter(text)
    assert fm["scope"] == ["**/*.svelte", "**/*.svelte.ts"]


def test_parse_frontmatter_no_frontmatter():
    text = "# Just a plain file\nno frontmatter here."
    assert parse_frontmatter(text) == {}


def test_parse_frontmatter_missing_scope():
    text = textwrap.dedent("""\
        ---
        name: my-agent
        effort: low
        ---
        # Body
    """)
    fm = parse_frontmatter(text)
    assert "scope" not in fm


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
        scope: always
        ---
        # Doc Review
    """))
    _write_agent(agents_dir, "svelte-review", textwrap.dedent("""\
        ---
        name: svelte-review
        description: Svelte
        effort: low
        scope:
          - **/*.svelte
        ---
        # Svelte Review
    """))
    rc = main.__wrapped__(agents_dir) if hasattr(main, "__wrapped__") else _call_main(agents_dir)
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
    # orchestrator has no scope: field — should be skipped
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
