#!/usr/bin/env python3
"""Compute the dispatched-but-not-returned set difference for a review roster (#1761).

`/code-review` Step 4 dispatches an agent roster and then has to notice when
one of them didn't come back with a contract-valid result. Today that
comparison is eyeballed by the orchestrator rather than computed — this
module is the deterministic half of the fix, mirroring `dispatch_waves.py`'s
own precedent of extracting a policy decision the orchestrator used to make
by inspection into a pure, testable function.

Pure policy — no filesystem, no network. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys


def reconcile_dispatch(dispatched: list[str], returned: set[str]) -> list[str]:
    """Return the names in ``dispatched`` that do not appear in ``returned``.

    Preserves ``dispatched``'s order and de-duplicates: a name repeated in
    ``dispatched`` is reported at most once, at its first-seen position. A
    name in ``returned`` that isn't in ``dispatched`` at all is ignored —
    this function only ever answers "who was dispatched but didn't come
    back," never "who came back unexpectedly." An empty ``dispatched``
    always yields ``[]``, never an error.
    """
    seen: set[str] = set()
    missing: list[str] = []
    for name in dispatched:
        if name in seen:
            continue
        seen.add(name)
        if name not in returned:
            missing.append(name)
    return missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dispatched", required=True,
        help="comma-separated agent names that were dispatched, in roster order",
    )
    parser.add_argument(
        "--returned", required=True,
        help="comma-separated agent names that returned a contract-valid result",
    )
    args = parser.parse_args(argv)

    dispatched = [a.strip() for a in args.dispatched.split(",") if a.strip()]
    returned = {a.strip() for a in args.returned.split(",") if a.strip()}

    missing = reconcile_dispatch(dispatched, returned)
    print(json.dumps({"missing": missing}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = ("reconcile_dispatch",)
