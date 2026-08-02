"""Tests for plugins/dev-team/hooks/lib/autoship_log.py."""

import json
import pathlib
import subprocess
import sys

# Ensure the lib module is importable from any working directory.
_LIB_DIR = (
    pathlib.Path(__file__).parent.parent.parent
    / "plugins"
    / "dev-team"
    / "hooks"
    / "lib"
)
sys.path.insert(0, str(_LIB_DIR))

from autoship_log import append_round


class TestAppendRound:
    def test_creates_new_file(self, tmp_path):
        log_file = tmp_path / "rounds.jsonl"
        assert not log_file.exists()

        append_round(str(log_file), {"round": 1})

        assert log_file.exists()

    def test_appends_multiple_lines(self, tmp_path):
        log_file = tmp_path / "rounds.jsonl"

        append_round(str(log_file), {"round": 1})
        append_round(str(log_file), {"round": 2})
        append_round(str(log_file), {"round": 3})

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_each_line_is_valid_json(self, tmp_path):
        log_file = tmp_path / "rounds.jsonl"

        append_round(str(log_file), {"round": 1, "status": "ok"})
        append_round(str(log_file), {"round": 2, "status": "skip"})

        for line in log_file.read_text(encoding="utf-8").strip().splitlines():
            parsed = json.loads(line)  # raises if invalid
            assert isinstance(parsed, dict)

    def test_each_line_has_logged_at(self, tmp_path):
        log_file = tmp_path / "rounds.jsonl"

        append_round(str(log_file), {"round": 1})
        append_round(str(log_file), {"round": 2})

        for line in log_file.read_text(encoding="utf-8").strip().splitlines():
            parsed = json.loads(line)
            assert "logged_at" in parsed, f"Missing logged_at in: {parsed}"

    def test_creates_parent_directories(self, tmp_path):
        log_file = tmp_path / "nested" / "deep" / "rounds.jsonl"

        append_round(str(log_file), {"round": 1})

        assert log_file.exists()

    def test_original_fields_preserved(self, tmp_path):
        log_file = tmp_path / "rounds.jsonl"
        record = {"round": 7, "agent": "autoship", "status": "complete"}

        append_round(str(log_file), record)

        parsed = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert parsed["round"] == 7
        assert parsed["agent"] == "autoship"
        assert parsed["status"] == "complete"

    def test_does_not_mutate_input_record(self, tmp_path):
        log_file = tmp_path / "rounds.jsonl"
        record = {"round": 1}

        append_round(str(log_file), record)

        assert "logged_at" not in record


class TestCLI:
    def _run(self, *args):
        module = str(_LIB_DIR / "autoship_log.py")
        return subprocess.run(
            [sys.executable, module, *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_creates_log_file(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"

        result = self._run(
            "--log-path",
            str(log_file),
            "--json",
            '{"round": 1, "source": "cli"}',
        )

        assert result.returncode == 0, result.stderr
        assert log_file.exists()

    def test_cli_appended_line_has_logged_at(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"

        self._run(
            "--log-path",
            str(log_file),
            "--json",
            '{"round": 1}',
        )

        parsed = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert "logged_at" in parsed

    def test_cli_invalid_json_exits_nonzero(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"

        result = self._run(
            "--log-path",
            str(log_file),
            "--json",
            "not-json",
        )

        assert result.returncode != 0

    def test_cli_non_object_json_exits_nonzero(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"

        result = self._run(
            "--log-path",
            str(log_file),
            "--json",
            "[1, 2, 3]",
        )

        assert result.returncode != 0

    def test_cli_appends_multiple_rounds(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"

        for i in range(3):
            self._run(
                "--log-path",
                str(log_file),
                "--json",
                json.dumps({"round": i}),
            )

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_cli_json_and_json_file_are_mutually_exclusive(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"
        json_file = tmp_path / "record.json"
        json_file.write_text('{"round": 1}', encoding="utf-8")

        result = self._run(
            "--log-path",
            str(log_file),
            "--json",
            '{"round": 1}',
            "--json-file",
            str(json_file),
        )

        assert result.returncode != 0

    def test_cli_requires_json_or_json_file(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"

        result = self._run("--log-path", str(log_file))

        assert result.returncode != 0


class TestJsonFileFlag:
    def _run(self, *args):
        module = str(_LIB_DIR / "autoship_log.py")
        return subprocess.run(
            [sys.executable, module, *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_json_file_appends_record(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"
        json_file = tmp_path / "record.json"
        json_file.write_text(
            '{"round_id": "r1", "issue": 42, "status": "shipped"}', encoding="utf-8"
        )

        result = self._run(
            "--log-path",
            str(log_file),
            "--json-file",
            str(json_file),
        )

        assert result.returncode == 0, result.stderr
        parsed = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert parsed["round_id"] == "r1"
        assert parsed["issue"] == 42
        assert parsed["status"] == "shipped"
        assert "logged_at" in parsed

    def test_json_file_with_agent_derived_special_characters(self, tmp_path):
        # The whole point of --json-file: text containing quotes/backslashes
        # that would break an inline --json shell string composes safely
        # when written to a file first.
        log_file = tmp_path / "cli-rounds.jsonl"
        json_file = tmp_path / "record.json"
        blocked_reason = 'needs "approval" from stakeholder; path C:\\data'
        json_file.write_text(
            json.dumps({"round_id": "r1", "blocked_reason": blocked_reason}),
            encoding="utf-8",
        )

        result = self._run(
            "--log-path",
            str(log_file),
            "--json-file",
            str(json_file),
        )

        assert result.returncode == 0, result.stderr
        parsed = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert parsed["blocked_reason"] == blocked_reason

    def test_json_file_invalid_json_exits_nonzero(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"
        json_file = tmp_path / "record.json"
        json_file.write_text("not-json", encoding="utf-8")

        result = self._run(
            "--log-path",
            str(log_file),
            "--json-file",
            str(json_file),
        )

        assert result.returncode != 0

    def test_json_file_nonexistent_path_exits_nonzero(self, tmp_path):
        log_file = tmp_path / "cli-rounds.jsonl"

        result = self._run(
            "--log-path",
            str(log_file),
            "--json-file",
            str(tmp_path / "does-not-exist.json"),
        )

        assert result.returncode != 0
        assert "--json-file" in result.stderr
