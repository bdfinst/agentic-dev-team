"""Unit tests for hooks/lib/telemetry_consent.py (#1405, Slice 1 Step 1.1)."""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import telemetry_consent


def test_no_home_config_file_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert telemetry_consent.is_enabled() is False


def test_home_config_enabled_true(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text('{"enabled":true}')
    assert telemetry_consent.is_enabled() is True


def test_home_config_enabled_false(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text('{"enabled":false}')
    assert telemetry_consent.is_enabled() is False


def test_home_config_malformed_json_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "telemetry.json").write_text("{not json")
    assert telemetry_consent.is_enabled() is False
