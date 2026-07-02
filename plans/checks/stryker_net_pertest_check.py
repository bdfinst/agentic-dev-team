#!/usr/bin/env python3
"""Structural RED/GREEN check for plans/stryker-net-pertest-coverage-analysis-default.md.

Documentation-only change — there is no runtime code path to exercise, so this
script IS the RED/GREEN gate for each TDD step. Run with `--step 1` or `--step 2`
to scope to that step's assertions, or no flag to run all.
"""

import argparse
import re
import sys
from pathlib import Path

TARGET = Path(
    "plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md"
)


def check_step_1(text: str) -> list:
    failures = []

    xunit_v3_idx = text.find("## xunit.v3 detection")
    pre_run_idx = text.find("## Pre-run: build first")
    if xunit_v3_idx == -1 or pre_run_idx == -1:
        failures.append(
            "anchor headings '## xunit.v3 detection' / '## Pre-run: build first' not found"
        )
        new_heading_idx = -1
    else:
        m = re.search(
            r"^## Default `coverage-analysis: perTest`.*$", text, re.MULTILINE
        )
        new_heading_idx = m.start() if m else -1

    if new_heading_idx == -1:
        failures.append(
            "item 1/new heading: no '## Default `coverage-analysis: perTest`...' section found"
        )
    else:
        section_end = text.find("\n## ", new_heading_idx + 1)
        if section_end == -1:
            section_end = len(text)
        section = text[new_heading_idx:section_end]

        if '"coverage-analysis": "perTest"' not in section:
            failures.append(
                'item 1: section does not contain "coverage-analysis": "perTest"'
            )

        if (
            "[#669](https://github.com/bdfinst/agentic-dev-team/issues/669)"
            not in section
        ):
            failures.append("item 2: no linked [#669](...) citation in section")

        if not re.search(r"xunit\.v2(-shim)?", section):
            failures.append("item 3: no mention of xunit.v2 / xunit.v2-shim")

        class_names = [
            "DataFormatter",
            "SystemConstants",
            "RequestContext",
            "PublicApiAttribute",
            "ComponentModule",
        ]
        has_class = any(name in section for name in class_names)
        has_parity = re.search(r"identical|same Killed count", section, re.IGNORECASE)
        if not (has_class and has_parity):
            failures.append(
                "item 4: missing a named experiment class alongside a parity phrase "
                "('identical' / 'same Killed count')"
            )

        has_reflection = "MethodInfo.Invoke" in section
        has_autofac = re.search(r"Autofac|container\.Resolve", section)
        has_outcome = re.search(
            r"checked out clean|no false negatives", section, re.IGNORECASE
        )
        if not (has_reflection and has_autofac and has_outcome):
            failures.append(
                "item 5: missing MethodInfo.Invoke + Autofac/container.Resolve mention "
                "alongside a 'checked out clean' / 'no false negatives' outcome phrase"
            )

        if not re.search(r"5[-–]6x", section):
            failures.append("item 6: no 5-6x (or 5–6x) speedup figure")

        if not re.search(
            r"does not apply to xunit\.v3|excludes xunit\.v3|not.{0,20}xunit\.v3",
            section,
            re.IGNORECASE,
        ):
            failures.append(
                "item 7: no explicit xunit.v3/MTP-runner exclusion statement"
            )

        if not (xunit_v3_idx < new_heading_idx < pre_run_idx):
            failures.append(
                f"item 8: placement out of order (xunit.v3={xunit_v3_idx}, "
                f"new={new_heading_idx}, pre-run={pre_run_idx})"
            )

        if not re.search(r"xunit\.v3 detection", section, re.IGNORECASE):
            failures.append(
                "item 9: no cross-reference to the 'xunit.v3 detection' heading"
            )

    return failures


def check_step_2(text: str) -> list:
    failures = []
    bash_blocks = re.findall(r"```bash(.*?)```", text, re.DOTALL)
    for block in bash_blocks:
        if "--coverage-analysis" in block:
            failures.append(
                "step 2: '--coverage-analysis' still present in a fenced bash block"
            )
            break

    if not re.search(
        r"config-file-only|only via the `?stryker-config\.json`? .{0,20}key|config.file only",
        text,
        re.IGNORECASE,
    ):
        failures.append(
            "step 2: no prose note stating coverage-analysis is config-file-only in Stryker.NET 4.15.0"
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["1", "2"], default=None)
    args = parser.parse_args()

    text = TARGET.read_text()
    failures = []
    if args.step in (None, "1"):
        failures += check_step_1(text)
    if args.step in (None, "2"):
        failures += check_step_2(text)

    if failures:
        print(f"FAIL ({len(failures)} check(s) failed):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS — all structural checks satisfied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
