"""The run ID that names a run and its artifact file."""

from __future__ import annotations

from datetime import datetime

RUN_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"
RUN_ID_RANDOM_BITS = 16
RUN_ID_RANDOM_HEX_DIGITS = RUN_ID_RANDOM_BITS // 4


def make_run_id(now: datetime, agent: str, model: str, effort: str, rng) -> str:
    """Return `<UTC time>-<agent>-<model>-<effort>-<4 random hex>`; `rng` needs `getrandbits`."""
    stamp = now.strftime(RUN_ID_TIME_FORMAT)
    suffix = f"{rng.getrandbits(RUN_ID_RANDOM_BITS):0{RUN_ID_RANDOM_HEX_DIGITS}x}"
    return f"{stamp}-{agent}-{model}-{effort}-{suffix}"
