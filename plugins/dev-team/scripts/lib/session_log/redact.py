"""The privacy boundary as a function, not a convention (issue #2045, epic
#2040).

Both extractors' own docstrings promise "metrics only — no prompt text,
code, file contents, or full command strings", and
``knowledge/telemetry-schema.md`` states the same contract. Before this
module existed, that promise was enforced only by every call site
individually remembering to run a name/path through
``classify.safe_name``/``classify.basename`` — a convention restated at (at
last count) seventeen call sites across ``scripts/session_extract.py``,
``plugins/dev-team/scripts/extract_session_report.py``, and
``session_log/signals.py``. That is exactly the shape that produced this
epic (#1990/#1991/#1994: the same defect landing independently in both
forked extractors because nothing forced a shared choke point). This module
is that choke point: one function, ``redact()``, that every field value
either extractor writes to its output passes through.

``redact()`` does not duplicate ``classify.safe_name``/``classify.basename``
— it composes them. Those two functions, and their Windows-path/allowlist
rationale, are unchanged and still individually tested; this module adds
the privacy-labeled entry point + the two-shape contract below, so a reader
(and a future call site) reaches for ``redact()`` by name rather than
re-deriving "should this be safe_name'd, basename'd, or both" from
scratch.

Real defect found while wiring this up (fixed in the same commit, not
paranoia): ``extract_session_report.py``'s ``_project_label`` used
``os.path.basename(os.path.normpath(cwd))`` instead of the shared,
Windows-path-aware ``classify.basename`` — on a POSIX host (where this
script runs), ``os.path.basename`` splits on ``/`` only, so a Windows-
authored transcript's backslash-separated ``cwd`` came back whole. It
did not leak the raw path (``classify.safe_name``'s allowlist has no
backslash in it, so the value collapsed to ``"other"``), but every such
project's label lost its real name — this is the exact defect class the
epic's own "why this is not paranoia" note warns about (``_basename``'s
Windows-path handling is a privacy fix a hand-port already dropped once),
found a third time by routing this call site through the shared primitive
instead of a bespoke one.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

from . import classify


def redact(value: str, *, from_path: bool = False) -> str:
    """The one function every name/label-shaped field value passes through
    before either extractor writes it to its emitted output.

    - ``from_path=True``: the caller KNOWS ``value`` is a filesystem path (a
      tool's ``file_path`` input, a transcript's ``cwd``) — strip to the
      last path component first (``classify.basename``), then apply the
      strict character allowlist (``classify.safe_name``).
    - ``from_path=False`` (default): apply the strict character allowlist
      directly, with NO path-stripping.

    Deliberately not "always basename first, regardless of what the value
    is" — a full shell command string like
    ``rm -rf /tmp/SENTINEL_CMD_do_not_leak`` would basename down to
    ``SENTINEL_CMD_do_not_leak`` (letters/underscores only, no slash), which
    WOULD then pass the allowlist: stripping everything before the last
    ``/`` can turn an unsafe string into one that only *looks* safe. The
    two-shape signature keeps that failure mode impossible — a value is
    only ever basenamed when the caller has affirmatively marked it as a
    path.

    A value that fails the allowlist collapses to ``"other"`` — never
    partial content, never raised. See ``classify.safe_name``'s own
    docstring for the allowlist rationale and ``classify.basename``'s for
    the Windows-path history (#1991/#1994) this composes on top of,
    unchanged."""
    if from_path:
        value = classify.basename(value)
    return classify.safe_name(value)
