"""Contract for gherkin_analysis_coverage_gate.py's Slice-2 behavior spec
(issue #1450) — the exit-0/exit-1/exit-2 acceptance scenarios named in
evals/skills/gherkin-derive-comprehensive-analysis-default/
slice-2-analysis-coverage-gate-script.feature.

Full unit coverage of the script's parsing internals lives alongside the
script itself, at
plugins/dev-team/tests/scripts/test_gherkin_analysis_coverage_gate.py
(this repo's convention for `plugins/dev-team/scripts/*.py` — see
gherkin_failure_path_gate.py's sibling test). This file is the
tests/skills/-rooted contract the repo's feature-spec guard
(tests/repo/test_feature_spec_refs.py) requires every evals/skills/*.feature
to cite, scoped to exactly the three scenarios the spec describes.
"""

from __future__ import annotations

import json
import sys

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_analysis_coverage_gate as gate

ALL_EIGHT_PRESENT = """## Analysis Coverage

- **Controllers**: OrdersController
- **Handlers**: none found in this codebase
- **Services**: OrderService
- **Domain logic**: Order aggregate
- **Workflows**: none found in this codebase
- **Validation rules**: total must be positive
- **Error handling**: mapped to 404
- **Business processes**: order fulfillment
"""

MISSING_DOMAIN_LOGIC = """## Analysis Coverage

- **Controllers**: OrdersController
- **Handlers**: none found in this codebase
- **Services**: OrderService
- **Workflows**: none found in this codebase
- **Validation rules**: total must be positive
- **Error handling**: mapped to 404
- **Business processes**: order fulfillment
"""

NO_SECTION = "# Surface inventory\n\nNo Analysis Coverage heading here.\n"


def test_scenario_all_eight_categories_recorded_exits_0(tmp_path):
    f = tmp_path / "gherkin.md"
    f.write_text(ALL_EIGHT_PRESENT)
    assert gate.main(["--file", str(f)]) == 0


def test_scenario_a_category_is_missing_exits_1_and_json_lists_it(tmp_path, capsys):
    f = tmp_path / "gherkin.md"
    f.write_text(MISSING_DOMAIN_LOGIC)
    exit_code = gate.main(["--file", str(f), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert "domain logic" in payload["missing"]


def test_scenario_no_analysis_coverage_section_found_exits_2(tmp_path):
    f = tmp_path / "gherkin.md"
    f.write_text(NO_SECTION)
    assert gate.main(["--file", str(f)]) == 2
