"""Unit tests for the Python port of hooks/lib/model-resolve.sh (#577).

Mirrors tests/hooks/model_resolve_tests.bats one-for-one. The two suites
run against sibling implementations of the same library-only slice — the
bash consumers (agent-model-resolve.sh, session-model-banner.sh,
scripts/build-worktree-baseref.sh) still source the .sh in this slice, so
byte-parity beyond stdout/stderr/exit code isn't yet enforced by the
parity harness; that arrives with the hook-level ports in #585-#587.

These tests are white-box: they call resolve_band/dump_map directly and
also exercise the CLI via subprocess to cover exit codes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

import model_resolve  # type: ignore[import-not-found]  # noqa: E402


_MODEL_LOW = "claude-haiku-4-5-20251001"
_MODEL_MEDIUM = "claude-sonnet-4-6"
_MODEL_HIGH = "claude-opus-4-8"


_DEFAULT_ROUTING = {
    "low": _MODEL_LOW,
    "medium": _MODEL_MEDIUM,
    "high": _MODEL_HIGH,
    "haiku": _MODEL_LOW,
    "sonnet": _MODEL_MEDIUM,
    "opus": _MODEL_HIGH,
    "rounding": "round_half_up",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def routing_json(tmp_path: Path) -> Path:
    """A default routing.json fixture that mirrors the shipped map.

    Decouples the test from drift in the shipped file (see the .bats sibling).
    """
    path = tmp_path / "routing.json"
    path.write_text(json.dumps(_DEFAULT_ROUTING) + "\n")
    return path


@pytest.fixture
def ladder_json(tmp_path: Path) -> Path:
    """A ladder path that does NOT exist yet — tests write to it as needed."""
    return tmp_path / "model-ladder.json"


@pytest.fixture
def resolver_env(monkeypatch, routing_json: Path, ladder_json: Path) -> None:
    """Wire the test-only injection seams to the fixture files."""
    monkeypatch.setenv("MODEL_ROUTING_JSON", str(routing_json))
    monkeypatch.setenv("MODEL_LADDER_JSON", str(ladder_json))


def _run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke the resolver CLI via a subprocess to cover main() and exit codes."""
    resolver = _HOOKS_LIB / "model_resolve.py"
    proc_env = dict(env) if env is not None else {}
    return subprocess.run(
        [sys.executable, str(resolver), *args],
        capture_output=True,
        env=proc_env,
        check=False,
    )


# ---------------------------------------------------------------------------
# Default map (no ladder) — migration safety
# ---------------------------------------------------------------------------


def test_low_band_resolves_to_haiku_default(
    routing_json: Path, ladder_json: Path
) -> None:
    assert (
        model_resolve.resolve_band(
            "low",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_LOW
    )


def test_medium_band_resolves_to_sonnet_default(
    routing_json: Path, ladder_json: Path
) -> None:
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_MEDIUM
    )


def test_high_band_resolves_to_opus_default(
    routing_json: Path, ladder_json: Path
) -> None:
    assert (
        model_resolve.resolve_band(
            "high",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_HIGH
    )


def test_no_ladder_bands_equal_pre_migration_snapshots(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    assert (
        model_resolve.resolve_band(
            "low",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_LOW
    )
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_MEDIUM
    )
    assert (
        model_resolve.resolve_band(
            "high",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_HIGH
    )


# ---------------------------------------------------------------------------
# Legacy tier acceptance (migration window) — tier → band normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tier,expected",
    [("haiku", _MODEL_LOW), ("sonnet", _MODEL_MEDIUM), ("opus", _MODEL_HIGH)],
)
def test_legacy_tier_normalizes_to_band(resolver_env, tier: str, expected: str) -> None:
    result = _run_cli(
        tier,
        env={
            "MODEL_ROUTING_JSON": _os_env_get("MODEL_ROUTING_JSON"),
            "MODEL_LADDER_JSON": _os_env_get("MODEL_LADDER_JSON"),
        },
    )
    assert result.returncode == 0
    assert result.stdout.decode().strip() == expected


def _os_env_get(name: str) -> str:
    """Read env set by monkeypatch — subprocess call needs the concrete value."""
    import os

    return os.environ[name]


# ---------------------------------------------------------------------------
# Caller errors
# ---------------------------------------------------------------------------


def test_unknown_band_exits_2_with_actionable_stderr(resolver_env) -> None:
    result = _run_cli(
        "frontier",
        env={
            "MODEL_ROUTING_JSON": _os_env_get("MODEL_ROUTING_JSON"),
            "MODEL_LADDER_JSON": _os_env_get("MODEL_LADDER_JSON"),
        },
    )
    assert result.returncode == 2
    stderr = result.stderr.decode()
    assert "Unknown" in stderr
    assert "low" in stderr
    assert "medium" in stderr
    assert "high" in stderr


def test_missing_band_argument_exits_2(resolver_env) -> None:
    result = _run_cli(
        env={
            "MODEL_ROUTING_JSON": _os_env_get("MODEL_ROUTING_JSON"),
            "MODEL_LADDER_JSON": _os_env_get("MODEL_LADDER_JSON"),
        }
    )
    assert result.returncode == 2


def test_caller_flag_accepted_and_ignored(resolver_env) -> None:
    result = _run_cli(
        "medium",
        "--caller",
        "naming-review",
        env={
            "MODEL_ROUTING_JSON": _os_env_get("MODEL_ROUTING_JSON"),
            "MODEL_LADDER_JSON": _os_env_get("MODEL_LADDER_JSON"),
        },
    )
    assert result.returncode == 0
    assert result.stdout.decode().strip() == _MODEL_MEDIUM


def test_unknown_flag_exits_2(resolver_env) -> None:
    result = _run_cli(
        "medium",
        "--frobnicate",
        env={
            "MODEL_ROUTING_JSON": _os_env_get("MODEL_ROUTING_JSON"),
            "MODEL_LADDER_JSON": _os_env_get("MODEL_LADDER_JSON"),
        },
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Ladder path — index = round_half_up(weight·(N−1))
# ---------------------------------------------------------------------------


def test_ladder_n3_reproduces_default_map(
    routing_json: Path, ladder_json: Path
) -> None:
    ladder_json.write_text(json.dumps([_MODEL_LOW, _MODEL_MEDIUM, _MODEL_HIGH]))
    assert (
        model_resolve.resolve_band(
            "low",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_LOW
    )
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_MEDIUM
    )
    assert (
        model_resolve.resolve_band(
            "high",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_HIGH
    )


def test_ladder_n2_low_to_sonnet_medium_and_high_to_opus(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text(json.dumps([_MODEL_MEDIUM, _MODEL_HIGH]))
    assert (
        model_resolve.resolve_band(
            "low",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_MEDIUM
    )
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_HIGH
    )
    assert (
        model_resolve.resolve_band(
            "high",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_HIGH
    )


def test_ladder_n1_collapses_every_band_to_single_model(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text(json.dumps([_MODEL_MEDIUM]))
    for band in ("low", "medium", "high"):
        assert (
            model_resolve.resolve_band(
                band,
                routing_path=routing_json,
                ladder_path=ladder_json,
            )
            == _MODEL_MEDIUM
        )


def test_ladder_n4_medium_lands_on_index_2_round_half_up(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text(
        json.dumps(
            [
                _MODEL_LOW,
                _MODEL_MEDIUM,
                _MODEL_HIGH,
                "claude-opusmax-9",
            ]
        )
    )
    assert (
        model_resolve.resolve_band(
            "low",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_LOW
    )
    # weight 0.5 * (4-1) + 0.5 = 2.0 → int() → 2 → opus
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_HIGH
    )
    # weight 1.0 * (4-1) + 0.5 = 3.5 → int() → 3 → opusmax
    assert (
        model_resolve.resolve_band(
            "high",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == "claude-opusmax-9"
    )


def test_ladder_feeds_legacy_tiers_too(routing_json: Path, ladder_json: Path) -> None:
    ladder_json.write_text(json.dumps([_MODEL_MEDIUM, _MODEL_HIGH]))
    # CLI path so we exercise legacy normalization + ladder together.
    result = _run_cli(
        "sonnet",
        env={
            "MODEL_ROUTING_JSON": str(routing_json),
            "MODEL_LADDER_JSON": str(ladder_json),
        },
    )
    assert result.returncode == 0
    assert result.stdout.decode().strip() == _MODEL_HIGH


# ---------------------------------------------------------------------------
# Malformed / degenerate ladder → degrade to the default map (never abort)
# ---------------------------------------------------------------------------


def test_malformed_ladder_invalid_json_degrades_to_default(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text("[not valid json")
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_MEDIUM
    )


def test_ladder_that_is_object_not_array_degrades_to_default(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text('{"low": "x"}')
    assert (
        model_resolve.resolve_band(
            "high",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_HIGH
    )


def test_empty_ladder_array_degrades_to_default(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text("[]")
    assert (
        model_resolve.resolve_band(
            "low",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_LOW
    )


def test_ladder_with_non_string_elements_degrades_to_default(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text(json.dumps([1, 2, 3]))
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_MEDIUM
    )


def test_ladder_with_mixed_string_and_non_string_degrades_to_default(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text(json.dumps([_MODEL_LOW, 42, _MODEL_HIGH]))
    assert (
        model_resolve.resolve_band(
            "medium",
            routing_path=routing_json,
            ladder_path=ladder_json,
        )
        == _MODEL_MEDIUM
    )


# ---------------------------------------------------------------------------
# Missing routing.json (the one surviving deny-relevant exit)
# ---------------------------------------------------------------------------


def test_missing_routing_json_exits_4_with_remediation(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    ladder = tmp_path / "ladder.json"
    result = _run_cli(
        "low",
        env={
            "MODEL_ROUTING_JSON": str(missing),
            "MODEL_LADDER_JSON": str(ladder),
        },
    )
    assert result.returncode == 4
    stderr = result.stderr.decode()
    assert "Model routing file missing:" in stderr
    assert "git checkout knowledge/model-routing.json" in stderr


# ---------------------------------------------------------------------------
# --dump-map flag
# ---------------------------------------------------------------------------


def test_dump_map_prints_three_bands_with_default_snapshots(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    output = model_resolve.dump_map(
        routing_path=routing_json,
        ladder_path=ladder_json,
    )
    for band in ("low", "medium", "high"):
        assert band in output
    for model in (_MODEL_LOW, _MODEL_MEDIUM, _MODEL_HIGH):
        assert model in output


def test_dump_map_reflects_ladder_when_present(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    ladder_json.write_text(json.dumps([_MODEL_MEDIUM, _MODEL_HIGH]))
    output = model_resolve.dump_map(
        routing_path=routing_json,
        ladder_path=ladder_json,
    )
    # low now resolves to sonnet (bottom of the ladder)
    assert _MODEL_MEDIUM in output
    # high still resolves to opus (top)
    assert _MODEL_HIGH in output


def test_dump_map_writes_no_files(routing_json: Path, ladder_json: Path) -> None:
    _ = model_resolve.dump_map(
        routing_path=routing_json,
        ladder_path=ladder_json,
    )
    assert not ladder_json.exists()


def test_dump_map_cli_exits_0(resolver_env) -> None:
    result = _run_cli(
        "--dump-map",
        env={
            "MODEL_ROUTING_JSON": _os_env_get("MODEL_ROUTING_JSON"),
            "MODEL_LADDER_JSON": _os_env_get("MODEL_LADDER_JSON"),
        },
    )
    assert result.returncode == 0
    stdout = result.stdout.decode()
    for band in ("low", "medium", "high"):
        assert band in stdout


def test_dump_map_format_matches_bash_printf(
    routing_json: Path,
    ladder_json: Path,
) -> None:
    """Format must be `  {band:<7} → {model}\\n` per band, no extras.

    Verifies byte-level format parity with the .sh's
    `printf '  %-7s → %s\\n'`.
    """
    output = model_resolve.dump_map(
        routing_path=routing_json,
        ladder_path=ladder_json,
    )
    lines = output.split("\n")
    assert lines[0] == f"  low     → {_MODEL_LOW}"
    assert lines[1] == f"  medium  → {_MODEL_MEDIUM}"
    assert lines[2] == f"  high    → {_MODEL_HIGH}"
    # final trailing newline → last element empty after split
    assert lines[3] == ""


# ---------------------------------------------------------------------------
# Internal helper coverage — normalize_band / _band_weight / _round_half_up
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token,expected",
    [
        ("low", "low"),
        ("haiku", "low"),
        ("medium", "medium"),
        ("sonnet", "medium"),
        ("high", "high"),
        ("opus", "high"),
        ("frontier", ""),
        ("", ""),
        ("LOW", ""),
    ],
)
def test_normalize_band(token: str, expected: str) -> None:
    # Public name (#732 dedup): agent_model_resolve.py calls this directly
    # instead of keeping its own drifted copy.
    assert model_resolve.normalize_band(token) == expected


# ---------------------------------------------------------------------------
# load_json — public so agent_model_resolve.py can call it directly (#732
# dedup). Regression coverage for the exception tuple the two copies had
# drifted on: agent_model_resolve.py's private copy additionally caught
# `ValueError` (covering e.g. UnicodeDecodeError from a mis-encoded file),
# which model_resolve.py's original did not. The shared implementation must
# have the broader (safer) tuple so both callers behave identically.
# ---------------------------------------------------------------------------


def test_load_json_returns_none_for_invalid_utf8(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe\x00\x00invalid")
    assert model_resolve.load_json(bad) is None


def test_load_json_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert model_resolve.load_json(tmp_path / "missing.json") is None


def test_load_json_returns_none_for_malformed_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    assert model_resolve.load_json(bad) is None


def test_load_json_returns_parsed_data(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"low": "x"}), encoding="utf-8")
    assert model_resolve.load_json(good) == {"low": "x"}


def test_ladder_is_valid_public_name(tmp_path: Path) -> None:
    ladder = tmp_path / "ladder.json"
    ladder.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert model_resolve.ladder_is_valid(ladder) is True
    assert model_resolve.ladder_is_valid(tmp_path / "missing.json") is False


@pytest.mark.parametrize(
    "band,weight",
    [("low", 0.0), ("medium", 0.5), ("high", 1.0)],
)
def test_band_weight(band: str, weight: float) -> None:
    assert model_resolve._band_weight(band) == weight


@pytest.mark.parametrize(
    "weight,n,expected",
    [
        # Reproduces the .sh's `awk 'printf "%d", int(w*(n-1)+0.5)'`
        (0.0, 3, 0),
        (0.5, 3, 1),
        (1.0, 3, 2),
        (0.0, 2, 0),
        (0.5, 2, 1),
        (1.0, 2, 1),
        (0.0, 1, 0),
        (0.5, 1, 0),
        (1.0, 1, 0),
        (0.0, 4, 0),
        (0.5, 4, 2),  # medium on N=4 → index 2 (round half up: 1.5 → 2)
        (1.0, 4, 3),
    ],
)
def test_round_half_up(weight: float, n: int, expected: int) -> None:
    assert model_resolve._round_half_up(weight, n) == expected
