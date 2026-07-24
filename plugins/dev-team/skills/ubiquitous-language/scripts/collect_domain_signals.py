#!/usr/bin/env python3
"""Python port of collect-domain-signals.sh (#617 / #572 Phase 3).

Gathers grep-based domain signals for the ubiquitous-language skill.

Deliberate divergence from the .sh: the shipped
`collect-domain-signals.sh` runs under `set -euo pipefail`, and every
section is a `{ safe_grep ... } | grep -v ... | sed ... | sort -u` pipe.
When any intermediate grep matches nothing (the common case for a real
project — e.g. no Java code), the pipe returns non-zero → pipefail →
`set -e` aborts. The script therefore stops after the first section, so
only `class-names.txt` is ever written in practice.

The .sh has zero bats coverage, so nothing tests (or depends on) the
broken early-exit. This port implements the six-section contract the
script's docstring + the ubiquitous-language SKILL.md both describe:
class names, enum values, domain events, BDD names, validator rules,
interface names — every section always runs and writes its file.

Usage: python3 collect_domain_signals.py [source-root]

Output: .plans/raw/domain-language/{class-names,enum-values,domain-events,
        bdd-names,validator-rules,interface-names}.txt

Uses `grep -rn --include=<glob> <pattern> -- <root>` under the hood (subprocess)
because reproducing bash grep -r's file walk + include semantics natively in
Python would drift on Windows line-endings and locale collation. The .sh is
authoritative; this port dispatches the same greps so both sides find the same
matches. Additional filtering + regex substitution is done in-process.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path


def _safe_grep(glob: str, pattern: str, root: str) -> list[str]:
    """`grep -rnE --include=<glob> <pattern> -- <root>`, silencing errors.

    The .sh runs plain `grep -rn`, which uses BRE and treats the ERE
    metachars in the shipped patterns (`(...|...)`, `[A-Z]+`) as
    literals — so the shipped .sh finds nothing and writes empty files
    on every real project. The port fixes this by using ERE (`grep -E`);
    the SKILL.md intent is a working signal collector, not a broken
    stub.
    """
    try:
        r = subprocess.run(
            ["grep", "-rnE", f"--include={glob}", pattern, "--", root],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return []
    if r.returncode not in (0, 1):
        # 0 = matches; 1 = no match; anything else is unexpected — treat as
        # no matches (the .sh does `|| true`).
        return []
    return [line for line in r.stdout.splitlines() if line]


def _sort_unique(lines: Iterable[str]) -> list[str]:
    return sorted(set(lines))


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(f"{line}\n" for line in lines))


# Repeated exclusion list from the .sh's `grep -v` chain.
_CLASS_EXCLUDES = re.compile(
    r"Test|Spec|Mock|Fake|Stub|Builder|Factory|Repository|Controller|Handler"
    r"|Middleware|Config|Settings|Helper|Util|Base|Abstract|Migration"
)

_INTERFACE_EXCLUDES = re.compile(
    r"Repository|Controller|Handler|Middleware|Factory|Builder|Config"
    r"|Logger|Cache|Queue|Bus|Mapper|Serializer|Parser"
)

# The .sh chains four `sed` substitutions to pull just the identifier out
# of a matched line. Each one strips everything up to a keyword then keeps
# only the [A-Z][a-zA-Z]* run and the trailing junk.
_NAME_EXTRACT_PATTERNS = [
    re.compile(r".*class ([A-Z][a-zA-Z]*).*"),
    re.compile(r".*interface ([A-Z][a-zA-Z]*).*"),
    re.compile(r".*struct ([A-Z][a-zA-Z]*).*"),
    re.compile(r".*record ([A-Z][a-zA-Z]*).*"),
]


def _extract_name(line: str) -> str:
    for pattern in _NAME_EXTRACT_PATTERNS:
        m = pattern.match(line)
        if m:
            return m.group(1)
    return line


def collect_class_names(root: str, out_dir: Path) -> int:
    print("  → class names...")
    raw: list[str] = []
    raw.extend(_safe_grep("*.ts", "^export (abstract )?class [A-Z][a-zA-Z]+", root))
    raw.extend(_safe_grep("*.ts", "^export (abstract )?interface [A-Z][a-zA-Z]+", root))
    raw.extend(
        _safe_grep(
            "*.cs",
            r"^[[:space:]]*(public|internal|sealed|abstract) (partial )?"
            r"(class|record|struct) [A-Z][a-zA-Z]+",
            root,
        )
    )
    raw.extend(
        _safe_grep(
            "*.java",
            "^public (abstract |final )?(class|interface|enum|record) [A-Z][a-zA-Z]+",
            root,
        )
    )
    raw.extend(_safe_grep("*.py", "^class [A-Z][a-zA-Z]+", root))
    raw.extend(_safe_grep("*.go", "^type [A-Z][a-zA-Z]+ struct", root))
    raw.extend(_safe_grep("*.go", "^type [A-Z][a-zA-Z]+ interface", root))
    raw.extend(_safe_grep("*.rb", "^class [A-Z][a-zA-Z]+", root))

    filtered = [line for line in raw if not _CLASS_EXCLUDES.search(line)]
    names = [_extract_name(line) for line in filtered]
    unique = _sort_unique(names)
    _write_lines(out_dir / "class-names.txt", unique)
    print(f"    {len(unique)} candidates")
    return len(unique)


def collect_enum_values(root: str, out_dir: Path) -> int:
    print("  → enum values...")
    raw: list[str] = []
    raw.extend(_safe_grep("*.ts", "^export (const )?enum [A-Z]", root))
    raw.extend(_safe_grep("*.cs", r"^[[:space:]]*(public|internal) enum [A-Z]", root))
    raw.extend(_safe_grep("*.java", "^public enum [A-Z]", root))
    raw.extend(
        _safe_grep("*.py", r"class [A-Z][a-zA-Z]*(Enum|Status|Type|State)\b", root)
    )
    raw.extend(_safe_grep("*.go", "// [A-Z][a-zA-Z]+ (is|represents|indicates)", root))
    unique = _sort_unique(raw)
    _write_lines(out_dir / "enum-values.txt", unique)
    print(f"    {len(unique)} candidates")
    return len(unique)


_EVENT_SUFFIXES = (
    "Created|Updated|Submitted|Approved|Cancelled|Rejected|Completed|Failed"
    "|Requested|Issued|Revoked|Expired|Activated|Deactivated|Shipped"
    "|Delivered|Refunded|Disputed"
)


def collect_domain_events(root: str, out_dir: Path) -> int:
    print("  → domain events...")
    raw: list[str] = []
    raw.extend(_safe_grep("*.ts", f"class [A-Z][a-zA-Z]*({_EVENT_SUFFIXES})", root))
    raw.extend(_safe_grep("*.cs", f"class [A-Z][a-zA-Z]*({_EVENT_SUFFIXES})", root))
    raw.extend(_safe_grep("*.java", f"class [A-Z][a-zA-Z]*({_EVENT_SUFFIXES})", root))
    raw.extend(
        _safe_grep("*.go", f"type [A-Z][a-zA-Z]*({_EVENT_SUFFIXES}) struct", root)
    )

    event_class = re.compile(r".*class ([A-Z][a-zA-Z]*).*")
    event_type = re.compile(r".*type ([A-Z][a-zA-Z]*) struct.*")
    names = []
    for line in raw:
        m = event_class.match(line) or event_type.match(line)
        names.append(m.group(1) if m else line)

    unique = _sort_unique(names)
    _write_lines(out_dir / "domain-events.txt", unique)
    print(f"    {len(unique)} candidates")
    return len(unique)


def collect_bdd_names(root: str, out_dir: Path) -> int:
    print("  → BDD names...")
    raw: list[str] = []
    # Gherkin keywords: `Scenario:`, `Given x`, `When y`, etc. — the
    # trailing char after the keyword is either whitespace or `:` (for
    # `Scenario` outlines / `Feature`). The .sh required trailing `\s`,
    # which never matches `Scenario:` — another bug we fix here.
    raw.extend(
        _safe_grep(
            "*.feature",
            r"^[[:space:]]*(Scenario|Given|When|Then|And)([[:space:]]|:)",
            root,
        )
    )
    raw.extend(_safe_grep("*.ts", "it\\(['\"].*['\"]", root))
    raw.extend(_safe_grep("*.ts", "describe\\(['\"].*['\"]", root))
    raw.extend(
        _safe_grep("*.cs", r"\[Fact\]|public void (Given|When|Then|Should)[A-Z]", root)
    )
    raw.extend(
        _safe_grep("*.java", r"@Test.*\n.*void (given|when|then|should)[A-Z]", root)
    )
    unique = _sort_unique(raw)
    _write_lines(out_dir / "bdd-names.txt", unique)
    print(f"    {len(unique)} candidates")
    return len(unique)


def collect_validator_rules(root: str, out_dir: Path) -> int:
    print("  → validator rules...")
    raw: list[str] = []
    # ERE alternation (matches grep -E): raw `|` is the alternation
    # operator, not the escaped BRE `\|` the .sh has (which grep -E treats
    # as a literal `|` character).
    raw.extend(
        _safe_grep(
            "*.ts",
            r"\.withMessage|\.mustBe|\.isRequired|z\.string\(\)\.refine|yup\.",
            root,
        )
    )
    raw.extend(
        _safe_grep("*.cs", r"RuleFor|\.Must|\.WithMessage|\.NotNull|\.NotEmpty", root)
    )
    raw.extend(
        _safe_grep(
            "*.java",
            r"@NotNull|@NotBlank|@Size|@Min|@Max|@Pattern|@Valid|@Constraint",
            root,
        )
    )
    raw.extend(
        _safe_grep("*.py", r"raise ValueError|raise TypeError|assert .*, ['\"]", root)
    )
    unique = _sort_unique(raw)
    _write_lines(out_dir / "validator-rules.txt", unique)
    print(f"    {len(unique)} candidates")
    return len(unique)


def collect_interface_names(root: str, out_dir: Path) -> int:
    print("  → interface names...")
    raw: list[str] = []
    raw.extend(_safe_grep("*.ts", "^export interface [A-Z][a-zA-Z]+", root))
    raw.extend(
        _safe_grep(
            "*.cs",
            r"^[[:space:]]*(public|internal) interface I[A-Z][a-zA-Z]+",
            root,
        )
    )
    raw.extend(_safe_grep("*.java", "^public interface [A-Z][a-zA-Z]+", root))
    raw.extend(_safe_grep("*.go", "type [A-Z][a-zA-Z]+ interface", root))

    filtered = [line for line in raw if not _INTERFACE_EXCLUDES.search(line)]
    iface_extract = re.compile(r".*interface (I?)([A-Z][a-zA-Z]*).*")
    names = []
    for line in filtered:
        m = iface_extract.match(line)
        names.append(m.group(2) if m else line)

    unique = _sort_unique(names)
    _write_lines(out_dir / "interface-names.txt", unique)
    print(f"    {len(unique)} candidates")
    return len(unique)


def main(argv: list) -> int:
    root = argv[1] if len(argv) > 1 else "."
    out_dir = Path(".plans/raw/domain-language")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Collecting domain signals from: {root}")

    collect_class_names(root, out_dir)
    collect_enum_values(root, out_dir)
    collect_domain_events(root, out_dir)
    collect_bdd_names(root, out_dir)
    collect_validator_rules(root, out_dir)
    collect_interface_names(root, out_dir)

    print()
    print(f"Signal collection complete. Results in {out_dir}/")

    # Total unique candidates across all txt files.
    combined = set()
    for txt in out_dir.glob("*.txt"):
        combined.update(txt.read_text().splitlines())
    combined.discard("")
    print(f"Total raw candidates: {len(combined)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
