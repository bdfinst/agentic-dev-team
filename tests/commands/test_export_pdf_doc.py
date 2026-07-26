"""Regression test for the security-assessment plugin's /export-pdf command.

The weasyprint fallback path renders Markdown that is ultimately derived
from a scanned repo or a probed model (`probe_08_report_generator.py`,
`service-comm-parser.py`) — untrusted input. weasyprint fetches remote
resources referenced in rendered HTML/CSS (`<img src="https://...">`, CSS
`url(...)`) by default, which is a plausible SSRF vector at PDF-conversion
time. The embedded conversion snippet must pass a `url_fetcher` that blocks
every non-local scheme.

This extracts the actual `_no_remote_fetch` guard defined in the command
doc and exercises it directly (with a stub `weasyprint.default_url_fetcher`)
so the test fails if the guard is removed, weakened, or never wired into
`HTML(...)`.
"""

from __future__ import annotations

import re
import sys
import types

import pytest

from _repo_root import REPO_ROOT

EXPORT_PDF = (
    REPO_ROOT / "plugins" / "security-assessment" / "commands" / "export-pdf.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return EXPORT_PDF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fallback_snippet(text: str) -> str:
    match = re.search(
        r"\*\*Fallback \(weasyprint \+ python-markdown\):\*\*.*?```bash\n(.*?)```",
        text,
        re.DOTALL,
    )
    assert match, "could not find the weasyprint fallback code block in export-pdf.md"
    return match.group(1)


def test_ships_export_pdf_md_command() -> None:
    assert EXPORT_PDF.is_file()


def test_fallback_snippet_defines_a_remote_fetch_guard(fallback_snippet: str) -> None:
    assert "_no_remote_fetch" in fallback_snippet
    assert "url_fetcher=_no_remote_fetch" in fallback_snippet


def test_remote_fetch_guard_blocks_https_and_allows_local(
    fallback_snippet: str,
) -> None:
    # Isolate just the guard function body (between "def _no_remote_fetch"
    # and the next top-level statement) and execute it against a stub
    # weasyprint module, so this test fails if the guard's logic itself is
    # ever weakened (e.g. an "or True", a scheme typo) even though the
    # string checks above still pass.
    func_match = re.search(
        r"def _no_remote_fetch\(.*?\n(?:    .*\n|\n)*", fallback_snippet
    )
    assert func_match, "could not isolate _no_remote_fetch function body"
    func_src = func_match.group(0)

    calls: list[str] = []

    def _stub_default_url_fetcher(url, *args, **kwargs):
        calls.append(url)
        return {"string": "<html></html>"}

    stub_weasyprint = types.ModuleType("weasyprint")
    stub_weasyprint.default_url_fetcher = _stub_default_url_fetcher
    sys.modules["weasyprint"] = stub_weasyprint
    try:
        namespace: dict = {}
        exec(func_src, namespace)  # noqa: S102 - exercising extracted doc code
        guard = namespace["_no_remote_fetch"]

        for blocked in (
            "https://evil.example.com/x.png",
            "http://169.254.169.254/latest/meta-data/",
        ):
            with pytest.raises(ValueError):
                guard(blocked)

        # Local/inline schemes must still be allowed through to the real
        # fetcher (this is a *safety* guard, not a functionality regression).
        guard("file:///tmp/report.css")
        guard("data:image/png;base64,AAAA")
        assert calls == ["file:///tmp/report.css", "data:image/png;base64,AAAA"]
    finally:
        del sys.modules["weasyprint"]
