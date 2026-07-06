"""No stale `context-summarization` references in the shipped plugin surface.

Issue #853 renamed the `context-summarization` skill to `handoff` (plus a
`fork` mode). Issue #907's post-merge integration test plan (item 8) checked
by hand that no reference to the old name survived the 20-PR merge batch —
several of those PRs were developed in parallel before #853 landed and could
plausibly have reintroduced a stale mention. This is that check made
permanent instead of re-run by hand every time.

Scope is deliberately the *shipped runtime surface* only
(`plugins/dev-team/{agents,skills,hooks,knowledge}`) — not the whole repo.
`docs/adr/` and similar historical/changelog material are expected to name
the old skill when recording the rename decision itself; flagging those
would be a false positive on the record of the change, not a drift.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

SCANNED_DIRS = ["agents", "skills", "hooks", "knowledge"]
STALE_NAME = "context-summarization"


def _shipped_text_files():
    for dirname in SCANNED_DIRS:
        root = PLUGIN_ROOT / dirname
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in (".md", ".py", ".json"):
                yield path


def test_no_stale_context_summarization_reference_in_shipped_surface() -> None:
    failures = []
    for path in _shipped_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if STALE_NAME in line.lower():
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
                )
    assert not failures, (
        "Stale 'context-summarization' reference(s) found in the shipped "
        "plugin surface (should say 'handoff' post-#853):\n" + "\n".join(failures)
    )
