"""Tests for scripts/scaffold_lint_config.py.

Every case builds a small project under tmp_path and runs the script's
``main`` on it, asserting what is written, what is printed, and which files
stay byte-identical.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scaffold_lint_config as scaffold
from scaffold_lint_config import main

PLUGIN_ROOT = SCRIPTS_DIR.parent
PAYLOAD_DIR = PLUGIN_ROOT / "templates" / "eslint" / "payload"
PLUGIN_VERSION = json.loads(
    (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
)["version"]
CONFIG_NAME = "eslint.devteam.config.js"
OLD_VERSION = "0.0.1"

USER_ESLINT_CONFIG = "export default [];\n"
USER_TSCONFIG = '{ "compilerOptions": {} }\n'


def make_project(
    root: Path,
    *,
    package_json: bool = True,
    js_source: bool = True,
    eslint_version: str | None = "9.0.0",
    declared_eslint: bool = True,
    flat_config: bool = True,
    legacy_config: bool = False,
) -> Path:
    """Build a project; each keyword names one gating input."""
    root.mkdir(parents=True, exist_ok=True)
    if package_json:
        deps = {"eslint": "^9.0.0"} if declared_eslint else {}
        (root / "package.json").write_text(
            json.dumps({"name": "demo", "devDependencies": deps}), encoding="utf-8"
        )
    if js_source:
        (root / "src").mkdir()
        (root / "src" / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    if eslint_version is not None:
        pkg = root / "node_modules" / "eslint"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(
            json.dumps({"name": "eslint", "version": eslint_version}), encoding="utf-8"
        )
    if flat_config:
        (root / "eslint.config.js").write_text(USER_ESLINT_CONFIG, encoding="utf-8")
        (root / "tsconfig.json").write_text(USER_TSCONFIG, encoding="utf-8")
    if legacy_config:
        (root / ".eslintrc.json").write_text("{}", encoding="utf-8")
    return root


def run(project: Path, capsys, *args: str) -> tuple[int, str]:
    code = main(["--project", str(project), *args])
    return code, capsys.readouterr().out


def snapshot(project: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(project)): p.read_bytes()
        for p in sorted(project.rglob("*"))
        if p.is_file()
    }


class TestPayloadConstants:
    def test_payload_names_match_the_payload_directory(self):
        on_disk = sorted(
            str(p.relative_to(PAYLOAD_DIR)).replace("\\", "/")
            for p in PAYLOAD_DIR.rglob("*")
            if p.is_file()
        )
        assert sorted(scaffold.PAYLOAD_FILES) == on_disk

    def test_hook_hardcoded_name_is_a_payload_file(self):
        assert CONFIG_NAME in scaffold.PAYLOAD_FILES


SUPPORTED_ROWS = [
    pytest.param({"eslint_version": "9.0.0"}, id="eslint-9-flat-config"),
    pytest.param({"eslint_version": "10.4.2"}, id="eslint-10-flat-config"),
    pytest.param({"eslint_version": "10.0.0-rc.1"}, id="eslint-10-prerelease"),
]

SKIP_ROWS = [
    pytest.param(
        {"eslint_version": "8.57.0"},
        ["8.57.0", "ESLint 9 or 10", "upgrade ESLint"],
        id="eslint-8",
    ),
    pytest.param(
        {"eslint_version": "11.0.0"},
        ["11.0.0", "ESLint 9 or 10", "unsupported"],
        id="eslint-11",
    ),
    pytest.param(
        {"eslint_version": None, "declared_eslint": True},
        ["declares ESLint", "not installed", "npm install"],
        id="declared-not-installed",
    ),
    pytest.param(
        {"eslint_version": None, "declared_eslint": False},
        ["ESLint is not installed", "npm install"],
        id="not-declared-not-installed",
    ),
    pytest.param(
        {"flat_config": False, "legacy_config": True},
        ["eslintrc", "flat config", "migrate"],
        id="legacy-eslintrc-only",
    ),
    pytest.param(
        {"flat_config": False, "legacy_config": False},
        ["no ESLint config", "eslint.config.js"],
        id="no-config-at-all",
    ),
    pytest.param(
        {"js_source": False},
        ["no JavaScript or TypeScript source", "Python"],
        id="python-repo-with-tooling-package-json",
    ),
    pytest.param(
        {"package_json": False},
        ["no package.json", "project root"],
        id="no-package-json",
    ),
]


class TestGating:
    @pytest.mark.parametrize("state", SUPPORTED_ROWS)
    def test_supported_state_writes_exactly_the_payload_files(
        self, tmp_path, capsys, state
    ):
        project = make_project(tmp_path / "p", **state)
        before = snapshot(project)
        code, out = run(project, capsys)
        assert code == 0
        after = snapshot(project)
        assert sorted(set(after) - set(before)) == sorted(scaffold.PAYLOAD_FILES)
        assert all(after[k] == v for k, v in before.items())
        for name in scaffold.PAYLOAD_FILES:
            assert f"written: {name}" in out

    @pytest.mark.parametrize(("state", "fragments"), SKIP_ROWS)
    def test_unsupported_state_writes_nothing_and_says_why_and_what_to_do(
        self, tmp_path, capsys, state, fragments
    ):
        project = make_project(tmp_path / "p", **state)
        before = snapshot(project)
        code, out = run(project, capsys)
        assert code == 0
        assert snapshot(project) == before
        assert "nothing written" in out
        reason = [l for l in out.splitlines() if l.startswith("reason: ")]
        action = [l for l in out.splitlines() if l.startswith("action: ")]
        assert len(reason) == 1 and len(action) == 1
        for fragment in fragments:
            assert fragment in out, f"{fragment!r} missing from:\n{out}"

    def test_version_comes_from_the_installed_package_not_package_json(
        self, tmp_path, capsys
    ):
        project = make_project(tmp_path / "p", eslint_version="8.57.0")
        # package.json claims ^9, node_modules holds 8.57.0: installed wins.
        _, out = run(project, capsys)
        assert "8.57.0" in out
        assert not (project / CONFIG_NAME).exists()

    def test_config_files_and_vendored_dirs_do_not_count_as_js_source(
        self, tmp_path, capsys
    ):
        project = make_project(tmp_path / "p", js_source=False)
        (project / "commitlint.config.js").write_text("export default {};\n")
        (project / "types.d.ts").write_text("export {};\n")
        (project / "node_modules" / "dep").mkdir()
        (project / "node_modules" / "dep" / "index.js").write_text("1\n")
        _, out = run(project, capsys)
        assert "nothing written" in out
        assert not (project / CONFIG_NAME).exists()

    def test_unreadable_package_json_is_a_skip_not_a_crash(self, tmp_path, capsys):
        project = make_project(tmp_path / "p")
        (project / "package.json").write_text("{not json", encoding="utf-8")
        code, out = run(project, capsys)
        assert code == 0
        assert "nothing written" in out and "package.json" in out


STAMP_LINE = re.compile(rb"^// devteam-lint v(\S+) sha256:([0-9a-f]{64})\n")


def scaffolded(tmp_path, capsys, **state) -> Path:
    project = make_project(tmp_path / "p", **state)
    run(project, capsys)
    return project


class TestStamp:
    def test_each_written_file_starts_with_the_stamp_over_the_payload_bytes(
        self, tmp_path, capsys
    ):
        project = scaffolded(tmp_path, capsys)
        for name in scaffold.PAYLOAD_FILES:
            content = (project / name).read_bytes()
            match = STAMP_LINE.match(content)
            assert match is not None
            assert match.group(1).decode() == PLUGIN_VERSION
            body = content[match.end() :]
            assert body == (PAYLOAD_DIR / name).read_bytes()
            assert match.group(2).decode() == hashlib.sha256(body).hexdigest()

    def test_body_hash_covers_bytes_exactly_so_crlf_changes_it(self):
        assert scaffold.body_hash(b"a\r\nb") != scaffold.body_hash(b"a\nb")

    def test_plugin_version_is_read_from_the_manifest(self, tmp_path):
        manifest = tmp_path / "plugin.json"
        manifest.write_text('{"version": "3.1.4"}', encoding="utf-8")
        assert scaffold.read_plugin_version(manifest) == "3.1.4"

    def test_unreadable_manifest_is_an_error(self, tmp_path):
        with pytest.raises(scaffold.ScaffoldError):
            scaffold.read_plugin_version(tmp_path / "missing.json")

    @pytest.mark.parametrize(
        ("raw", "major"),
        [("9.0.0", 9), ("10.4.2", 10), ("10.0.0-rc.1", 10), ("v9", None), ("", None)],
    )
    def test_parse_major(self, raw, major):
        assert scaffold.parse_major(raw) == major

    def test_user_eslint_config_and_tsconfig_stay_byte_identical(
        self, tmp_path, capsys
    ):
        project = scaffolded(tmp_path, capsys)
        assert (project / "eslint.config.js").read_text() == USER_ESLINT_CONFIG
        assert (project / "tsconfig.json").read_text() == USER_TSCONFIG


class TestIdempotentRerun:
    def test_edited_file_is_never_overwritten_and_is_reported_as_existing(
        self, tmp_path, capsys
    ):
        project = scaffolded(tmp_path, capsys)
        target = project / CONFIG_NAME
        target.write_bytes(target.read_bytes() + b"// my edit\n")
        before = snapshot(project)
        code, out = run(project, capsys)
        assert code == 0
        assert snapshot(project) == before
        assert f"skipped (exists): {CONFIG_NAME}" in out

    def test_second_run_is_byte_identical_for_an_unedited_file(self, tmp_path, capsys):
        project = scaffolded(tmp_path, capsys)
        before = snapshot(project)
        run(project, capsys)
        assert snapshot(project) == before

    def test_summary_names_mode_and_next_steps(self, tmp_path, capsys):
        project = make_project(tmp_path / "p")
        _, out = run(project, capsys)
        assert "mode: untyped" in out
        assert "untyped misses:" in out
        assert "DEVTEAM_POST_LINT=1" in out
        assert 'import devteam from "./eslint.devteam.config.js"' in out

    def test_typed_mode_when_tsconfig_and_dependencies_are_installed(
        self, tmp_path, capsys
    ):
        project = make_project(tmp_path / "p")
        for dep in scaffold.TYPED_DEPENDENCIES:
            (project / "node_modules" / Path(dep)).mkdir(parents=True)
        _, out = run(project, capsys)
        assert "mode: typed" in out
        assert "untyped misses:" not in out


def write_state(project: Path, state: str) -> bytes:
    """Write the config file in one of the five check states; return its bytes."""
    body = (PAYLOAD_DIR / CONFIG_NAME).read_bytes()
    edited = body + b"// my edit\n"
    stamped_current = scaffold.stamp(PLUGIN_VERSION, body)
    stamped_old = scaffold.stamp(OLD_VERSION, body)
    content = {
        "current": stamped_current,
        "stale-unedited": stamped_old,
        "stale-edited": scaffold.make_stamp_line(OLD_VERSION, body) + edited,
        "current-edited": scaffold.make_stamp_line(PLUGIN_VERSION, body) + edited,
        "unstamped": body,
    }[state]
    (project / CONFIG_NAME).write_bytes(content)
    return content


STATES = ["current", "stale-unedited", "stale-edited", "current-edited", "unstamped"]


class TestCheck:
    @pytest.mark.parametrize("state", STATES)
    def test_check_reports_the_status_and_changes_nothing(
        self, tmp_path, capsys, state
    ):
        project = make_project(tmp_path / "p")
        write_state(project, state)
        before = snapshot(project)
        code, out = run(project, capsys, "--check")
        assert code == 0
        assert json.loads(out) == {CONFIG_NAME: state}
        assert snapshot(project) == before

    def test_check_on_an_unscaffolded_project_reports_no_files(self, tmp_path, capsys):
        project = make_project(tmp_path / "p")
        code, out = run(project, capsys, "--check")
        assert code == 0
        assert json.loads(out) == {}

    def test_check_does_not_need_the_project_to_pass_the_scaffold_gate(
        self, tmp_path, capsys
    ):
        project = make_project(tmp_path / "p", eslint_version="8.57.0")
        write_state(project, "stale-unedited")
        _, out = run(project, capsys, "--check")
        assert json.loads(out) == {CONFIG_NAME: "stale-unedited"}

    def test_a_crlf_conversion_of_the_body_counts_as_edited(self, tmp_path, capsys):
        project = make_project(tmp_path / "p")
        body = (PAYLOAD_DIR / CONFIG_NAME).read_bytes()
        crlf = body.replace(b"\n", b"\r\n")
        (project / CONFIG_NAME).write_bytes(
            scaffold.make_stamp_line(PLUGIN_VERSION, body) + crlf
        )
        _, out = run(project, capsys, "--check")
        assert json.loads(out) == {CONFIG_NAME: "current-edited"}


class TestRefresh:
    @pytest.mark.parametrize("state", [s for s in STATES if s != "stale-unedited"])
    def test_every_state_but_stale_unedited_stays_byte_identical(
        self, tmp_path, capsys, state
    ):
        project = make_project(tmp_path / "p")
        content = write_state(project, state)
        code, out = run(project, capsys, "--refresh")
        assert code == 0
        assert (project / CONFIG_NAME).read_bytes() == content
        assert json.loads(out)["refreshed"] == []

    def test_stale_unedited_is_rewritten_with_the_current_stamp(self, tmp_path, capsys):
        project = make_project(tmp_path / "p")
        write_state(project, "stale-unedited")
        code, out = run(project, capsys, "--refresh")
        assert code == 0
        assert json.loads(out)["refreshed"] == [CONFIG_NAME]
        assert (project / CONFIG_NAME).read_bytes() == scaffold.stamp(
            PLUGIN_VERSION, (PAYLOAD_DIR / CONFIG_NAME).read_bytes()
        )
        _, after = run(project, capsys, "--check")
        assert json.loads(after) == {CONFIG_NAME: "current"}

    def test_stale_edited_is_left_alone_and_listed(self, tmp_path, capsys):
        project = make_project(tmp_path / "p")
        content = write_state(project, "stale-edited")
        _, out = run(project, capsys, "--refresh")
        assert (project / CONFIG_NAME).read_bytes() == content
        assert json.loads(out)["skipped"] == {CONFIG_NAME: "stale-edited"}

    def test_check_and_refresh_are_mutually_exclusive(self, tmp_path):
        with pytest.raises(SystemExit) as exit_info:
            main(["--project", str(tmp_path), "--check", "--refresh"])
        assert exit_info.value.code == 2
