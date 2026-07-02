"""hooks/token_efficiency_review.py's _check_source_file() used to read the
target file twice: once via _line_count() (read_bytes) and again via
_long_functions() (read_text) for the same path. This locks the existing
line-count / long-function-detection behavior and then asserts the file
content is only read from disk once per _check_source_file() call.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "token_efficiency_review.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("token_efficiency_review", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["token_efficiency_review"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


tef = _load_module()


def test_long_source_file_still_warns(tmp_path: Path) -> None:
    long_js = tmp_path / "long.js"
    long_js.write_text("\n".join(f"// line {i}" for i in range(600)))
    warnings = tef._check_source_file(long_js)
    assert any("File is 600 lines" in w for w in warnings)


def test_long_function_still_detected(tmp_path: Path) -> None:
    src = tmp_path / "longfn.js"
    body = "\n".join(f"  console.log({i});" for i in range(60))
    src.write_text(f"function bigOne() {{\n{body}\n}}\n")
    warnings = tef._check_source_file(src)
    assert any("Long functions detected" in w for w in warnings)
    assert any("bigOne" in w for w in warnings)


def test_check_source_file_reads_the_file_from_disk_only_once(
    tmp_path: Path, monkeypatch
) -> None:
    src = tmp_path / "sample.py"
    src.write_text("\n".join(f"def f{i}(): pass" for i in range(20)))

    read_calls = {"count": 0}
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text

    def counting_read_bytes(self, *a, **kw):
        if self == src:
            read_calls["count"] += 1
        return real_read_bytes(self, *a, **kw)

    def counting_read_text(self, *a, **kw):
        if self == src:
            read_calls["count"] += 1
        return real_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr(Path, "read_text", counting_read_text)

    tef._check_source_file(src)

    assert read_calls["count"] == 1, (
        f"expected _check_source_file to read {src} from disk exactly once, "
        f"got {read_calls['count']}"
    )
