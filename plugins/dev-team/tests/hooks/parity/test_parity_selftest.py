"""Self-test for the parity harness itself.

Uses two throwaway hook impls (a `.sh` and a `.py`) that ARE byte-identical
in behavior — assert_parity passes. Then a mutated `.py` that diverges —
assert_parity fails. This is the harness's own smoke test; it does not
touch any real hook.

Also exercises the sandbox isolation contract from
`docs/python-hook-contract.md`: env vars scrubbed, tmpdir-scoped, no
side effects outside the sandbox.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from parity import (  # type: ignore[import-not-found]
    Fixture,
    assert_parity,
    dispatch,
    record_fixture,
)


def _write_matched_pair(tmpdir: Path) -> tuple[Path, Path]:
    sh = tmpdir / "echo.sh"
    py = tmpdir / "echo.py"
    sh.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            # Echo argv joined by space, then a fixed line to stderr.
            printf '%s\\n' "$*"
            printf 'diag pid=%s ts=2026-07-02T00:00:00Z\\n' "$$" >&2
            exit 0
            """
        )
    )
    py.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os, sys
            print(" ".join(sys.argv[1:]))
            print(f"diag pid={os.getpid()} ts=2026-07-02T00:00:00Z", file=sys.stderr)
            sys.exit(0)
            """
        )
    )
    sh.chmod(0o755)
    py.chmod(0o755)
    return sh, py


def test_dispatch_captures_stdout_and_exit_code(tmp_path: Path) -> None:
    sh, _ = _write_matched_pair(tmp_path)
    result = dispatch(
        ["bash", str(sh), "hello", "world"],
        stdin_bytes=b"",
        env={"HOME": str(tmp_path)},
        cwd=tmp_path,
    )
    assert result.exit_code == 0
    assert result.stdout == b"hello world\n"


def test_assert_parity_passes_on_matched_pair(tmp_path: Path) -> None:
    sh, py = _write_matched_pair(tmp_path)
    fixture = Fixture(
        name="matched-echo",
        stdin=b"",
        argv=["hi", "there"],
        env={},
    )
    assert_parity(
        sh_argv=["bash", str(sh), *fixture.argv],
        py_argv=["python3", str(py), *fixture.argv],
        fixture=fixture,
    )


def test_assert_parity_fails_on_divergent_stdout(tmp_path: Path) -> None:
    sh, py = _write_matched_pair(tmp_path)
    # Break the .py's stdout on purpose.
    py.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys
            print("DIVERGENT")
            sys.exit(0)
            """
        )
    )
    fixture = Fixture(name="broken-echo", stdin=b"", argv=["hi"], env={})
    with pytest.raises(AssertionError):
        assert_parity(
            sh_argv=["bash", str(sh), *fixture.argv],
            py_argv=["python3", str(py), *fixture.argv],
            fixture=fixture,
        )


def test_assert_parity_fails_on_divergent_exit_code(tmp_path: Path) -> None:
    sh, py = _write_matched_pair(tmp_path)
    py.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(7)\n")
    fixture = Fixture(name="wrong-exit", stdin=b"", argv=[], env={})
    with pytest.raises(AssertionError):
        assert_parity(
            sh_argv=["bash", str(sh)],
            py_argv=["python3", str(py)],
            fixture=fixture,
        )


def test_stderr_normalization_strips_timestamps_pids_tmpdir(tmp_path: Path) -> None:
    """Two impls that only differ in timestamp/PID/tmpdir prefixes must match."""
    sh = tmp_path / "diag.sh"
    py = tmp_path / "diag.py"
    sh.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'ok\\n'\n"
        "printf 'ts=2026-07-02T12:34:56Z pid=1234 path=%s/x.log\\n' \"$PWD\" >&2\n"
        "exit 0\n"
    )
    py.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "print('ok')\n"
        "cwd = os.environ.get('PWD') or os.getcwd()\n"
        "print(f'ts=2026-07-02T99:99:99Z pid=99999 path={cwd}/x.log', file=sys.stderr)\n"
        "sys.exit(0)\n"
    )
    fixture = Fixture(name="stderr-norm", stdin=b"", argv=[], env={})
    assert_parity(
        sh_argv=["bash", str(sh)],
        py_argv=["python3", str(py)],
        fixture=fixture,
    )


def test_sandbox_isolation_scrubs_git_config_env(tmp_path: Path) -> None:
    """Hook run under the harness must see GIT_CONFIG_GLOBAL=/dev/null."""
    py = tmp_path / "probe.py"
    py.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "print(os.environ.get('GIT_CONFIG_GLOBAL', '<unset>'))\n"
        "sys.exit(0)\n"
    )
    fixture = Fixture(name="probe", stdin=b"", argv=[], env={})
    result = dispatch(
        ["python3", str(py)],
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        cwd=tmp_path,
        sandbox=True,
    )
    assert result.stdout.decode().strip() == "/dev/null"


def test_record_fixture_writes_snapshot_from_sh(tmp_path: Path) -> None:
    """--record mode regenerates expected.json from the .sh run."""
    import json

    sh, _ = _write_matched_pair(tmp_path)
    fixture = Fixture(name="recorded", stdin=b"", argv=["one", "two"], env={})
    snap = tmp_path / "snapshots" / "recorded.json"
    assert not snap.exists()
    written = record_fixture(
        sh_argv=["bash", str(sh), *fixture.argv],
        fixture=fixture,
        snapshot_path=snap,
    )
    assert written == snap
    data = json.loads(snap.read_text())
    assert data["name"] == "recorded"
    assert data["exit_code"] == 0
    assert data["stdout"] == "one two\n"
    # stderr_normalized should have the timestamp and pid substituted.
    assert "<TS>" in data["stderr_normalized"]
    assert "pid=<PID>" in data["stderr_normalized"]


def test_parity_record_cli_option_registered(pytestconfig) -> None:  # type: ignore[no-untyped-def]
    """The --parity-record flag exists on the pytest CLI."""
    # If registration failed, `getoption` would raise ValueError.
    _ = pytestconfig.getoption("--parity-record")


def test_side_effect_tree_snapshot_detects_divergent_files(tmp_path: Path) -> None:
    """.sh writes foo, .py writes bar — assert_parity fails on tree divergence."""
    sh = tmp_path / "writer.sh"
    py = tmp_path / "writer.py"
    sh.write_text('#!/usr/bin/env bash\necho content > "$1/foo.txt"\nexit 0\n')
    py.write_text(
        '#!/usr/bin/env python3\nimport sys\nopen(sys.argv[1] + "/bar.txt","w").write("content\\n")\nsys.exit(0)\n'
    )
    fixture = Fixture(name="tree-mismatch", stdin=b"", argv=["SANDBOX"], env={})
    with pytest.raises(AssertionError):
        assert_parity(
            sh_argv=["bash", str(sh)],
            py_argv=["python3", str(py)],
            fixture=fixture,
        )
