"""Shared helper for the stack-aware-*.py suites (ported from the
stack-aware-*.bats files, issue #675).

body_only() strips YAML frontmatter delimited by --- markers, triple-
backtick fenced code blocks, and inline backtick spans from a skill/agent
body, mirroring each bats file's duplicated `body_only()` awk helper. Used
for negative-grep assertions that must ignore language names appearing in
worked examples, frontmatter `cites:` lists, or `inline code` references.
"""

from __future__ import annotations

import re

# BANNED_TOKENS: language-specific tokens that must NOT appear in
# skill/agent body prose. Mirrored across the three stack-aware ports —
# keep in sync. Bare 'C#' and '.NET' are deliberately excluded: they appear
# in legitimate language-list contexts (e.g. naming which language
# test-file indicators the agent supports).
BANNED_TOKENS_RE = re.compile(r"csharp|dotnet|HttpClient|HttpMessageHandler")


def body_only(text: str) -> str:
    lines = text.splitlines()
    out = []
    in_fm = False
    in_fence = False
    first = True
    for line in lines:
        if line == "---":
            if first:
                in_fm = True
                first = False
                continue
            if in_fm:
                in_fm = False
                continue
        if in_fm:
            continue
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)
