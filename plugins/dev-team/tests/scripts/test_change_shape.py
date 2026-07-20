"""Unit tests for skills/code-review/scripts/change_shape.py (#1254).

Covers the deterministic change-shape gate: when a changeset has no runtime
surface (docs/config only), the low-yield lenses (performance, correctness) are
skipped; any runtime surface (source, unknown extension, functional Claude
config) keeps them. Fail-safe: unknown = runtime surface.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import change_shape  # noqa: E402


class TestHasRuntimeSurface:
    def test_source_file_has_runtime_surface(self):
        assert change_shape.has_runtime_surface(["src/app.py"]) is True
        assert change_shape.has_runtime_surface(["src/app.ts", "README.md"]) is True

    def test_docs_only_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface(["README.md", "docs/guide.rst"]) is False

    def test_config_only_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface(
            ["config.json", "app.yaml", ".gitignore", "settings.toml"]
        ) is False

    def test_docs_and_config_mixed_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface(["CHANGELOG.md", "ci.yml"]) is False

    def test_unknown_extension_is_runtime_surface_failsafe(self):
        # A file we cannot prove is doc/config must count as runtime surface,
        # so the code lenses still run (fail-safe).
        assert change_shape.has_runtime_surface(["Makefile"]) is True
        assert change_shape.has_runtime_surface(["thing.rb"]) is True

    def test_functional_claude_config_is_runtime_surface(self):
        # Markdown under agents/skills/etc. drives behavior — never "just docs".
        for f in [
            "agents/security-review.md",
            "skills/plan/SKILL.md",
            "knowledge/agent-registry.md",
            ".claude/settings.json",
            "CLAUDE.md",
            "AGENTS.md",
            "templates/agents/python.md",
        ]:
            assert change_shape.has_runtime_surface([f]) is True, f

    def test_empty_changeset_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface([]) is False
        assert change_shape.has_runtime_surface(["", "  "]) is False


class TestLensesToSkip:
    def test_docs_only_skips_low_yield_lenses(self):
        skip = change_shape.lenses_to_skip(["README.md", "config.json"])
        assert skip == ["performance-review", "correctness-review"]

    def test_runtime_surface_skips_nothing(self):
        assert change_shape.lenses_to_skip(["src/app.py", "README.md"]) == []

    def test_empty_changeset_skips_nothing(self):
        assert change_shape.lenses_to_skip([]) == []


class TestCli:
    def test_cli_docs_only_reports_skip(self, capsys):
        rc = change_shape.main(["--files", "README.md", "config.yaml"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hasRuntimeSurface"] is False
        assert out["skipLenses"] == ["performance-review", "correctness-review"]

    def test_cli_runtime_surface_reports_no_skip(self, capsys):
        rc = change_shape.main(["--files", "src/main.go"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hasRuntimeSurface"] is True
        assert out["skipLenses"] == []

    def test_cli_files_from_stdin(self, capsys, monkeypatch):
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO("docs/a.md\nb.json\n"))
        rc = change_shape.main(["--files-from", "-"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["skipLenses"] == ["performance-review", "correctness-review"]
