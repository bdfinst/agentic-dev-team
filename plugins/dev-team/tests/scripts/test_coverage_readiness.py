"""Tests for scripts/coverage_readiness.py (issue #1086)."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_readiness import (  # noqa: E402
    build_report,
    detect_runner,
    main,
    resolve_config_source,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


def pkg(root: Path, data: dict) -> None:
    write(root / "package.json", data)


# ---------------------------------------------------------------------------
# runner detection
# ---------------------------------------------------------------------------

def test_detect_runner_none_without_package_json(tmp_path):
    assert detect_runner(tmp_path, None) is None


def test_detect_runner_jest_from_dependency(tmp_path):
    data = {"devDependencies": {"jest": "^29"}}
    assert detect_runner(tmp_path, data) == "jest"


def test_detect_runner_angular_jest_preset(tmp_path):
    data = {"devDependencies": {"@angular-builders/jest": "^18", "jest-preset-angular": "^14"}}
    assert detect_runner(tmp_path, data) == "jest"


def test_detect_runner_vitest_from_dependency(tmp_path):
    assert detect_runner(tmp_path, {"devDependencies": {"vitest": "^2"}}) == "vitest"


def test_detect_runner_config_file_beats_absent_dep(tmp_path):
    write(tmp_path / "jest.config.js", "module.exports = {}")
    assert detect_runner(tmp_path, {}) == "jest"


def test_detect_runner_vite_config_needs_vitest_dep(tmp_path):
    write(tmp_path / "vite.config.ts", "export default {}")
    assert detect_runner(tmp_path, {}) is None
    assert detect_runner(tmp_path, {"devDependencies": {"vitest": "^2"}}) == "vitest"


# ---------------------------------------------------------------------------
# config source resolution
# ---------------------------------------------------------------------------

def test_resolve_prefers_config_file_over_package_json(tmp_path):
    write(tmp_path / "jest.config.js", "module.exports = {}")
    src, kind = resolve_config_source(tmp_path, "jest", {"jest": {}})
    assert src == "jest.config.js"
    assert kind == "js"


def test_resolve_package_json_jest_key(tmp_path):
    src, kind = resolve_config_source(tmp_path, "jest", {"jest": {"coverageReporters": []}})
    assert src == "package.json#jest"
    assert kind == "json"


def test_resolve_json_config_is_patchable_kind(tmp_path):
    write(tmp_path / "jest.config.json", {"coverageReporters": ["lcov"]})
    src, kind = resolve_config_source(tmp_path, "jest", None)
    assert (src, kind) == ("jest.config.json", "json")


def test_resolve_none_when_no_config(tmp_path):
    assert resolve_config_source(tmp_path, "jest", {}) == (None, "none")


# ---------------------------------------------------------------------------
# the reproduction case from #1086 — Angular/Jest, no json-summary, no scope
# ---------------------------------------------------------------------------

def test_angular_jest_not_ready(tmp_path):
    pkg(tmp_path, {"devDependencies": {"@angular-builders/jest": "^18"}})
    write(
        tmp_path / "jest.config.js",
        "module.exports = { coverageReporters: ['lcov', 'clover', 'json'] };",
    )
    report = build_report(tmp_path, patch=False)
    assert report["runner"] == "jest"
    assert report["config_kind"] == "js"
    assert report["has_json_summary"] is False
    assert report["ready"] is False
    assert report["has_scope"] is False
    assert report["reporter_hint"] and "json-summary" in report["reporter_hint"]
    assert report["scope_hint"] and "collectCoverageFrom" in report["scope_hint"]
    # JS configs are never auto-rewritten, even with --patch.
    patched = build_report(tmp_path, patch=True)
    assert patched["patched"] is False
    assert patched["ready"] is False


def test_js_config_with_json_summary_is_ready(tmp_path):
    pkg(tmp_path, {"devDependencies": {"jest": "^29"}})
    write(
        tmp_path / "jest.config.js",
        "module.exports = { coverageReporters: ['json-summary'], collectCoverageFrom: ['src/**/*.ts'] };",
    )
    report = build_report(tmp_path, patch=False)
    assert report["ready"] is True
    assert report["meaningful"] is True
    assert report["reporter_hint"] is None
    assert report["scope_hint"] is None


# ---------------------------------------------------------------------------
# patching JSON-shaped configs
# ---------------------------------------------------------------------------

def test_patch_package_json_jest_key(tmp_path):
    pkg(
        tmp_path,
        {
            "devDependencies": {"jest": "^29"},
            "jest": {"coverageReporters": ["lcov", "clover", "json"]},
        },
    )
    report = build_report(tmp_path, patch=True)
    assert report["patched"] is True
    assert report["ready"] is True
    data = json.loads((tmp_path / "package.json").read_text())
    reporters = data["jest"]["coverageReporters"]
    assert "json-summary" in reporters
    # existing reporters preserved
    assert reporters[:3] == ["lcov", "clover", "json"]


def test_patch_jest_config_json(tmp_path):
    pkg(tmp_path, {"devDependencies": {"jest": "^29"}})
    write(tmp_path / "jest.config.json", {"coverageReporters": ["lcov"]})
    report = build_report(tmp_path, patch=True)
    assert report["patched"] is True
    assert report["ready"] is True
    data = json.loads((tmp_path / "jest.config.json").read_text())
    assert "json-summary" in data["coverageReporters"]


def test_patch_creates_reporters_when_absent(tmp_path):
    pkg(tmp_path, {"devDependencies": {"jest": "^29"}, "jest": {}})
    report = build_report(tmp_path, patch=True)
    assert report["patched"] is True
    data = json.loads((tmp_path / "package.json").read_text())
    assert "json-summary" in data["jest"]["coverageReporters"]


def test_patch_idempotent_when_already_present(tmp_path):
    pkg(tmp_path, {"devDependencies": {"jest": "^29"}, "jest": {"coverageReporters": ["json-summary"]}})
    report = build_report(tmp_path, patch=True)
    assert report["patched"] is False
    assert report["ready"] is True


def test_patch_vitest_json_is_reported_not_written(tmp_path):
    # Vitest config is always JS/TS in practice; a hypothetical JSON path still
    # patches deterministically, but the common case is a JS file left to the
    # confirmed edit path.
    pkg(tmp_path, {"devDependencies": {"vitest": "^2"}})
    write(tmp_path / "vitest.config.ts", "export default { test: { coverage: { reporter: ['text'] } } }")
    report = build_report(tmp_path, patch=True)
    assert report["config_kind"] == "js"
    assert report["patched"] is False
    assert report["ready"] is False
    assert "json-summary" in report["reporter_hint"]


# ---------------------------------------------------------------------------
# vitest object detection
# ---------------------------------------------------------------------------

def test_vitest_scope_detected_from_include(tmp_path):
    pkg(tmp_path, {"devDependencies": {"vitest": "^2"}})
    write(
        tmp_path / "vitest.config.ts",
        "export default { test: { coverage: { reporter: ['json-summary'], include: ['src/**'] } } }",
    )
    report = build_report(tmp_path, patch=False)
    assert report["runner"] == "vitest"
    assert report["ready"] is True
    assert report["meaningful"] is True


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------

def test_main_exit_2_when_not_js(tmp_path, capsys):
    rc = main([str(tmp_path)])
    assert rc == 2
    assert json.loads(capsys.readouterr().out)["ready"] is False


def test_main_exit_1_when_not_ready(tmp_path, capsys):
    pkg(tmp_path, {"devDependencies": {"jest": "^29"}})
    write(tmp_path / "jest.config.js", "module.exports = { coverageReporters: ['lcov'] }")
    assert main([str(tmp_path)]) == 1


def test_main_exit_0_after_patch(tmp_path, capsys):
    pkg(tmp_path, {"devDependencies": {"jest": "^29"}, "jest": {"coverageReporters": ["lcov"]}})
    assert main([str(tmp_path), "--patch"]) == 0
    assert json.loads(capsys.readouterr().out)["ready"] is True


def test_main_exit_1_no_runner(tmp_path, capsys):
    pkg(tmp_path, {"dependencies": {"left-pad": "^1"}})
    assert main([str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["runner"] is None
