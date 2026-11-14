"""Apply each listed mutant to a copy of the project and require the tests to kill it.

Exit 0 when the unmutated tests pass and every mutant in mutants.json makes them
fail; exit 1 otherwise, naming each surviving mutant.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_COMMAND = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]


def tests_pass(project: Path) -> bool:
    completed = subprocess.run(TEST_COMMAND, cwd=project, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def main() -> int:
    if not tests_pass(ROOT):
        print("the unmutated tests fail", file=sys.stderr)
        return 1
    mutants = json.loads((ROOT / "mutants" / "mutants.json").read_text())
    survivors = []
    for mutant in mutants:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "project"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("__pycache__"))
            target = copy / mutant["file"]
            source = target.read_text()
            if source.count(mutant["find"]) != 1:
                print(f"mutant {mutant['id']} no longer applies", file=sys.stderr)
                return 1
            target.write_text(source.replace(mutant["find"], mutant["replace"]))
            if tests_pass(copy):
                survivors.append(mutant["id"])
    if survivors:
        print(f"surviving mutants: {', '.join(survivors)}", file=sys.stderr)
        return 1
    print(f"all {len(mutants)} mutants killed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
