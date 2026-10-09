"""The package imports with only its own directory on the path."""

from __future__ import annotations

import subprocess
import sys

from model_effort import external, paths

from _repo_root import REPO_ROOT


def _run_isolated(body: str) -> subprocess.CompletedProcess:
    """Run `body` in an interpreter whose path holds only the package's parent directory."""
    code = (
        "import importlib, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts' / 'lib')!r})\n" + body
    )
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )


class TestPackageImportsOnItsOwn:
    def test_every_module_imports_with_only_the_package_directory_on_the_path(self):
        modules = sorted(
            f"model_effort.{path.stem}"
            for path in (REPO_ROOT / "scripts" / "lib" / "model_effort").glob("*.py")
            if path.stem != "__init__"
        )

        completed = _run_isolated(
            f"for name in {modules!r}:\n    importlib.import_module(name)\n"
        )

        assert completed.returncode == 0, completed.stderr

    def test_every_reused_script_loads_and_answers_with_only_the_package_directory_on_the_path(
        self,
    ):
        completed = _run_isolated(
            "from model_effort import external\n"
            "for loader in (external.agent_contract_validator, external.isolated_dispatch,\n"
            "               external.minimal_yaml, external.pricing, external.eval_grade):\n"
            "    loader()\n"
            "external.load_for_run()\n"
            "assert external.contract_enums() is not None\n"
            "assert external.should_scrub_env_var('CLAUDE_CODE_SESSION_ID') is True\n"
            "assert external.should_scrub_env_var('HOME') is False\n"
        )

        assert completed.returncode == 0, completed.stderr

    def test_the_reused_modules_load_by_path_and_are_cached(self):
        assert external.minimal_yaml().parse_yaml("a: 1") == {"a": 1}
        assert external.pricing().load_pricing(paths.PRICING_PATH)["models"]
        assert callable(external.eval_grade().run_grading)
        assert external.pricing() is external.pricing()
