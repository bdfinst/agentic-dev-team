"""session_log — the shared classification/discovery core for the two
forked session-transcript extractors (epic #2040):

  - ``scripts/session_extract.py`` (monorepo-only developer tooling)
  - ``plugins/dev-team/scripts/extract_session_report.py`` (shipped)

See ``docs/adr/0036-the-two-session-extractors-stay-forked-1994.md`` for why
the extractors themselves stay forked (discovery/CLI surface, pricing, cost,
rollup, escalation, and report shapes legitimately differ) while this
package exists to hold what does NOT legitimately differ: the classification
logic both scripts computed independently, drifted on, and shipped the same
missing-41%-of-spend defect in twice (#1990/#1991/#1994).

Import direction (ADR 0032 purity): every module in this package is
stdlib-only (Python 3.10+, per ADR 0014/0015) and imports nothing from
either extractor script. Both extractors import FROM ``session_log``, never
the reverse.

Modules:
  discovery  transcript path classification and enumeration
  records    JSONL record iteration, the usage-block read contract, slimming
  classify   text/name classification vocabulary (issue #2043)
  signals    per-record signal accumulation (issue #2044)
  pricing    model-pricing loader, rate lookup, cost computation (issue #2045)
  redact     the privacy boundary as a function, not a convention (issue #2045)
"""

from __future__ import annotations
