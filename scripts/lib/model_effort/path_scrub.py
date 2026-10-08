"""Keep machine-specific paths out of text that is stored in the committed artifact."""

from __future__ import annotations

import tempfile
from pathlib import Path

HOME_PLACEHOLDER = "~"
TEMP_PLACEHOLDER = "<tmp>"
STAGED_PLACEHOLDER = "<staged>"
# A prefix this short would rewrite unrelated text, as when HOME is "/".
MIN_PREFIX_CHARS = 2


def scrub_paths(text: str, staged_dir: Path | None) -> str:
    """Replace the home, temp and staged directories in `text` with placeholders.

    Both the path as given and its resolved spelling are replaced, because the CLI
    reports the directory it sees, which may be the symlink-resolved one. Longer
    prefixes go first, so a home or staged directory inside the temp directory
    keeps its more specific placeholder.
    """
    replacements = [
        (prefix, placeholder)
        for directory, placeholder in (
            (staged_dir, STAGED_PLACEHOLDER),
            (Path(tempfile.gettempdir()), TEMP_PLACEHOLDER),
            (_home_dir(), HOME_PLACEHOLDER),
        )
        if directory is not None
        for prefix in _spellings(directory)
        if len(prefix) >= MIN_PREFIX_CHARS
    ]
    for prefix, placeholder in sorted(replacements, key=lambda pair: -len(pair[0])):
        text = text.replace(prefix, placeholder)
    return text


def _spellings(directory: Path) -> set[str]:
    return {str(directory), str(directory.resolve())}


def _home_dir() -> Path | None:
    try:
        return Path.home()
    except RuntimeError:  # no home directory can be determined
        return None
