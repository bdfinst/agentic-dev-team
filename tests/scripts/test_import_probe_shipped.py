"""tests for scripts/import_probe_shipped.py — the "Python floor" CI job's
actual import-time check (#1681).

No test file existed for this script before #1681: a blanket `ImportError`
exclusion (documented as "a path artifact of this probe rather than something
a user would hit") silently swallowed a genuine version-floor violation —
`from datetime import UTC` (3.11+) reported "all shipped modules import
cleanly" on a real 3.10 interpreter. Found by manually proving the newly
raised floor gate (ADR 0031) could fail before trusting it, per this repo's
own CLAUDE.md rule — exactly the situation a test file should have already
covered.

These tests import `import_probe_shipped.py` as a module (not subprocess) so
`_is_version_error` can be exercised directly with synthetic exceptions,
alongside one end-to-end subprocess test proving the fixed classification
survives contact with `main()`'s actual exception handling.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "import_probe_shipped.py"


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("import_probe_shipped_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def probe():
    return _load_probe_module()


class TestIsVersionError:
    """Unit coverage of the classifier `main()` dispatches through."""

    @pytest.mark.parametrize(
        "exc",
        [
            SyntaxError("bad syntax"),
            TypeError("'type' object is not subscriptable"),
            AttributeError("module has no attribute"),
            NameError("name is not defined"),
            ValueError("bad value"),
        ],
    )
    def test_the_original_denylist_types_are_still_caught(self, probe, exc):
        """These are unambiguous regardless of ImportError's own nuance —
        never touched by #1681, must not regress."""
        assert probe._is_version_error(exc) is True

    def test_module_not_found_error_is_excluded(self, probe):
        """The sibling sys.path miss this probe's harness can genuinely
        produce — a `ModuleNotFoundError` for a whole missing module, not a
        version signal."""
        exc = ModuleNotFoundError("No module named 'some_sibling'")
        exc.name = "some_sibling"
        assert probe._is_version_error(exc) is False

    def test_a_stdlib_symbol_missing_below_the_floor_is_included(self, probe):
        """#1681's actual bug shape: a plain ImportError whose `.name`
        resolves to a real STDLIB module — the shape `from datetime import
        UTC` (3.11+) produces on a pre-3.11 interpreter. Manufactured rather
        than triggered via a real `datetime.UTC` import so the property is
        exercised regardless of which interpreter runs this suite — the
        interpreter-dependent version is covered separately below."""
        exc = ImportError("cannot import name 'UTC' from 'datetime'")
        exc.name = "datetime"
        assert "datetime" in sys.stdlib_module_names
        assert probe._is_version_error(exc) is True

    def test_the_real_datetime_utc_case_on_a_pre_311_interpreter(self, probe):
        """Integration proof that the manufactured case above matches what a
        real interpreter actually raises. Skips on 3.11+, where the import
        succeeds and there is nothing to reproduce — the property itself
        stays covered, unskippable, by the test above."""
        try:
            from datetime import UTC  # noqa: F401
        except ImportError as exc:
            assert type(exc) is ImportError
            assert exc.name == "datetime"
            assert probe._is_version_error(exc) is True
        else:
            pytest.skip("this interpreter already has datetime.UTC (3.11+)")

    def test_a_relative_import_harness_artifact_is_excluded(self, probe):
        """`from . import x` executed via spec_from_file_location (no known
        parent package) is a plain ImportError with `.name is None` — a
        probe-harness artifact (four real shipped mutation adapters hit this
        shape today), not a version signal."""
        try:
            exec(  # noqa: S102 - manufacturing a specific ImportError shape, not real code
                compile("from . import nonexistent", "<relative-import>", "exec"),
                {"__name__": "not_a_package_member"},
            )
        except ImportError as exc:
            assert type(exc) is ImportError
            assert exc.name is None
            assert probe._is_version_error(exc) is False
        else:
            pytest.fail("expected a relative-import ImportError")

    def test_a_project_local_name_collision_is_excluded(self, probe):
        """The subtler case #1681's fix had to add beyond a bare `e.name is
        not None` check: a plain ImportError whose `.name` resolves to a
        PROJECT-LOCAL module (not stdlib) is still excluded. Reproduces the
        real collision found in this repo's own tree: `codebase_recon.py`'s
        `from lib import deterministic_recon` failing with `e.name == "lib"`
        because this probe's shared, never-reset sys.path let an unrelated
        same-named sibling (`hooks/mutation_adapters/lib.py`) shadow the
        intended `scripts/lib/` package — a probe-harness artifact, not
        anything to do with the interpreter version."""
        exc = ImportError("cannot import name 'deterministic_recon' from 'lib'")
        exc.name = "lib"
        assert "lib" not in sys.stdlib_module_names
        assert probe._is_version_error(exc) is False

    def test_a_non_import_exception_is_never_misclassified(self, probe):
        assert probe._is_version_error(OSError("disk full")) is False
        assert probe._is_version_error(RuntimeError("unrelated")) is False


class TestEndToEnd:
    """Prove the classification survives contact with `main()`, not just the
    helper in isolation — a synthetic shipped-tree fixture, run as the real
    subprocess entry point."""

    def test_a_genuine_version_violation_fails_the_probe(self, tmp_path):
        """End-to-end proof that `main()`'s exception handling actually
        dispatches through `_is_version_error` and fails the run — not just
        that the helper classifies correctly in isolation.

        The fixture module directly constructs and raises the exact
        exception shape #1681 was about (plain ImportError, `.name` set to a
        real stdlib module) rather than importing a version-specific symbol
        like `datetime.UTC` — deterministic regardless of which interpreter
        runs this test, unlike an approach that needs a genuinely
        version-gated stdlib difference to reproduce."""
        fixture_root = tmp_path / "plugins" / "dev-team" / "scripts"
        fixture_root.mkdir(parents=True)
        (fixture_root / "uses_missing_stdlib_symbol.py").write_text(
            "_exc = ImportError(\"cannot import name 'UTC' from 'datetime'\")\n"
            '_exc.name = "datetime"\n'
            "raise _exc\n",
            encoding="utf-8",
        )

        script_text = SCRIPT.read_text(encoding="utf-8")
        patched = script_text.replace(
            'REPO_ROOT = Path(__file__).resolve().parent.parent\n',
            f'REPO_ROOT = Path({str(tmp_path)!r})\n',
        )
        assert patched != script_text, "REPO_ROOT assignment line not found to patch"
        patched_script = tmp_path / "import_probe_shipped_patched.py"
        patched_script.write_text(patched, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(patched_script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "failed to import" in result.stderr
        assert "uses_missing_stdlib_symbol.py" in result.stderr

    def test_a_probe_harness_artifact_does_not_fail_the_probe(self, tmp_path):
        """The other half of the end-to-end proof: a plain ImportError whose
        `.name` is NOT a stdlib module (the `codebase_recon.py`/`lib`
        collision shape) must not fail the run, matching the unit-level
        `test_a_project_local_name_collision_is_excluded` above."""
        fixture_root = tmp_path / "plugins" / "dev-team" / "scripts"
        fixture_root.mkdir(parents=True)
        (fixture_root / "hits_a_project_local_collision.py").write_text(
            "_exc = ImportError(\"cannot import name 'thing' from 'lib'\")\n"
            '_exc.name = "lib"\n'
            "raise _exc\n",
            encoding="utf-8",
        )

        script_text = SCRIPT.read_text(encoding="utf-8")
        patched = script_text.replace(
            'REPO_ROOT = Path(__file__).resolve().parent.parent\n',
            f'REPO_ROOT = Path({str(tmp_path)!r})\n',
        )
        patched_script = tmp_path / "import_probe_shipped_patched.py"
        patched_script.write_text(patched, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(patched_script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "all shipped modules import cleanly" in result.stdout

    def test_a_clean_fixture_tree_passes(self, tmp_path):
        fixture_root = tmp_path / "plugins" / "dev-team" / "scripts"
        fixture_root.mkdir(parents=True)
        (fixture_root / "ordinary_module.py").write_text(
            textwrap.dedent(
                """
                def add(a, b):
                    return a + b
                """
            ),
            encoding="utf-8",
        )

        script_text = SCRIPT.read_text(encoding="utf-8")
        patched = script_text.replace(
            'REPO_ROOT = Path(__file__).resolve().parent.parent\n',
            f'REPO_ROOT = Path({str(tmp_path)!r})\n',
        )
        patched_script = tmp_path / "import_probe_shipped_patched.py"
        patched_script.write_text(patched, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(patched_script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "all shipped modules import cleanly" in result.stdout
