# 31. Raise the shipped Python floor from 3.8 to 3.10

Date: 2026-08-01

## Status

Accepted, supersedes ADR 0014's "Minimum Python version" design question and
its version-numbered consequences. ADR 0014's other decisions (Python over
bash, stdlib-only, phased conversion) are unaffected.

## Context

ADR 0014 set the shipped floor at Python 3.8, justified entirely by OS
availability: "3.8 is EOL upstream, but is the floor most operating systems
still support (Ubuntu 20.04 LTS, macOS Homebrew, Windows Python.org)."

That premise has since expired:

| | |
| --- | --- |
| Python 3.8 EOL | Oct 2024 |
| Ubuntu 20.04 LTS standard support ended | May 2025 (ESM only thereafter) |
| **Python 3.9 EOL** | **Oct 2025** |
| Python 3.10 EOL | Oct 2026 |

The floor sat two EOL releases below anything upstream-supported, and the
specific OS that justified it (Ubuntu 20.04) is out of standard support.
Homebrew and python.org both default to 3.11+ today.

The floor is not free to hold. It is enforced by a dedicated CI job ("Python
3.8 floor" in `.github/workflows/plugin-tests.yml`), `chk_python_floor` in
`scripts/ci-local.sh`, `scripts/import_probe_shipped.py`, and
`ruff.toml`'s `[per-file-target-version]` split — which stops ruff
autofixing shipped code into syntax the floor can't run. It has produced two
real incidents: `dict | dict` in `cost_meter.py` (the hand-maintained-denylist
era the gate itself now exists to replace) and `asyncio.to_thread` in
`orchestrator.py` (issue #1650, still open — the gate byte-compiles and
imports but doesn't exercise function bodies, so a runtime-only API used
inside a function stays invisible to it regardless of which version the
floor is pinned to).

Filed as issue #1679 after a session working the #1638 heredoc-normalizer
follow-ups needed `MappingProxyType`/`NamedTuple` care specifically because
of the 3.8 constraint, and separately noticed the constraint's justification
no longer matched anything true about the world.

### Design questions

1. **Which floor?** 3.9, 3.10, and 3.11 were considered.
   - **3.9** clears the immediate EOL complaint but is itself EOL (Oct 2025)
     — the floor would still be one step behind every upstream-supported
     release, just less badly than 3.8.
   - **3.10** — **chosen**. Covers Ubuntu 22.04 LTS (the oldest LTS still in
     standard support, through Apr 2027) while getting native `X | None`,
     `match` statements, `Path.is_relative_to`, and the modern
     `collections.abc` generic surface. Itself EOL Oct 2026, so this is a
     revisit-when-that-date-approaches choice, not a permanent one.
   - **3.11** — rejected for now. Matches what every currently-supported OS
     actually ships and would retire the `[per-file-target-version]` split
     entirely, but drops RHEL 9's default `python3` (3.9) and Ubuntu 22.04's
     default (3.10) outright. A larger compatibility cut than this pass
     wanted to make in one step.

2. **What to do with the 301 shipped files' "Python 3.8+" docstring lines?**
   - **Rewrite all 301 to "3.10+".** Considered. Keeps the per-file claim
     honest, but creates 301 more lines that will need updating again the
     next time the floor moves, and nothing enforces that they stay in sync
     with `ruff.toml`'s actual `per-file-target-version` value in the
     meantime — a second, prose copy of a fact one config value already
     states machine-checkably.
   - **Drop the per-file version claim entirely — chosen.** `ruff.toml`'s
     `[per-file-target-version]` and the CI job's interpreter are the single
     source of truth for what the floor IS; a docstring is a copy that can
     drift and isn't checked against either. The "stdlib-only" half of each
     docstring line is retained where it appeared — that fact doesn't change
     with the floor and is worth keeping visible file-by-file.

## Decision

**The shipped floor (`plugins/dev-team/**`) is Python 3.10, stdlib-only.**
Concretely:

- `ruff.toml`: `target-version` (repo-root tooling) raised `py39` → `py311`;
  `[per-file-target-version]` for `plugins/dev-team/**` raised `py38` →
  `py310`.
- `scripts/ci-local.sh`'s `chk_python_floor`, `scripts/dev-setup.sh`'s
  interpreter provisioning, and `scripts/import_probe_shipped.py` all resolve
  and report a 3.10 interpreter instead of 3.8.
- Every shipped `.py` file's "Python 3.8+" docstring line is removed, not
  rewritten to "3.10+" (see design question 2). Comments that existed to
  justify a 3.8-specific workaround (`str.removeprefix`/`removesuffix`
  avoided, `dict`-merge avoided, `Path.is_relative_to` avoided,
  `collections.abc` generic subscripting avoided) are corrected or removed —
  several of those workarounds are now unnecessary and were simplified in the
  same pass (`stryker_shard_setup.py`'s `_is_within_root` now uses
  `Path.is_relative_to` directly).
- `plugins/dev-team/CLAUDE.md`, `docs/developer-notes.md`, and the
  mutation-testing skill docs are updated to state 3.10, citing this ADR
  alongside ADR 0014/0015.
- ADR 0014's own "Minimum Python version" bullet and its "Documented as ≥ 3.8
  baseline" consequence are superseded by this ADR; its other content stands.

## Consequences

- **Native `X | None`, `list[...]`/`dict[...]` at runtime, `match` statements,
  and `Path.is_relative_to` become available in shipped code without a
  `from __future__ import annotations` workaround or a manual `try/except
  ValueError` substitute.** `ruff --fix` immediately modernized ~74 call sites
  across the repo the moment the target moved, which is the intended effect
  of `[per-file-target-version]` existing as a real (not aspirational)
  constraint.
- **Downstream operators on RHEL 9's default `python3` (3.9) or an
  unsupported/EOL Ubuntu 20.04 lose compatibility.** Anyone on 3.9 needs an
  alternate interpreter (`uv python install 3.10`, pyenv, or their
  distribution's backport) — the same shape of ask ADR 0014 already made of
  3.8-only environments.
- **The floor is EOL again in ~14 months (Oct 2026).** This ADR does not fix
  the underlying pattern — a fixed floor drifts toward EOL by construction —
  it only resets the clock. A future revisit should consider whether the
  floor should track "N-2 supported CPython minors" as a standing policy
  rather than a number re-chosen by hand each time.
- **#1650 was not resolved by this ADR, but was subsequently closed.** At the
  time this ADR was accepted, the floor gate only byte-compiled and imported;
  it could not see a runtime-only API used inside a function body, regardless
  of which version it targeted. `chk_python_floor` (`scripts/ci-local.sh`)
  now also actually runs, under the resolved floor interpreter via `uv run
  --python`, the test slice covering the shipped agent scripts — closing that
  blind spot for the scripts it covers. It remains a slice, not the full
  suite, so a runtime-only API misused in a shipped script outside that
  slice would still reproduce #1650's original failure mode.
- **`ruff.toml`'s global `target-version` (repo-root tooling, not user-facing)
  moves `py39` → `py311`**, matching this container's actual interpreter
  (3.11.15) and every currently-supported OS default. Repo-root scripts may
  now use `datetime.UTC` and other 3.11-only stdlib surface; shipped code may
  not — the split still holds, just at different numbers.

## Alternatives considered

- **No floor at all** (delete the gate, `ruff.toml` split, CI job, and
  `import_probe_shipped.py`). Rejected: a user on an older interpreter would
  get a runtime crash with no warning, which is the exact failure #1650 and
  the gate's own origin story (`dict | dict` reaching `main` clean) exist to
  prevent. Removing the gate doesn't remove the compatibility question, it
  just stops answering it.
- **Track "oldest non-EOL CPython" as a moving target** rather than a fixed
  number. Attractive in principle but needs its own mechanism (something has
  to compute "current non-EOL floor" and update `ruff.toml` on a schedule);
  out of scope for this pass, noted above as a real gap this ADR leaves open.

## References

- Issue #1679 — this ADR's originating issue, including the EOL-date table
- Issue #1650 — the floor gate's blind spot to runtime-only API usage;
  independent of which version the floor targets
- ADR 0014 — `docs/adr/0014-python-for-cross-os-scripts.md` (superseded in
  part by this ADR)
- ADR 0015 — `docs/adr/0015-bash-removal-complete.md` (unaffected)
- `tests/repo/test_python_floor.py` — pins the floor version, ADR reference,
  and CI job together; updated alongside this ADR
