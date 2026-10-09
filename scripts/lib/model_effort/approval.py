"""The spend-approval gate: decide whether the operator allows the run to start."""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

PROMPT = "Proceed? [y/N] "
AFFIRMATIVE_ANSWERS = frozenset({"y", "yes"})
NO_TTY_MESSAGE = "approval required and stdin is not a TTY: rerun with --yes"
DECLINED_MESSAGE = (
    "declined at the prompt, so no trial ran: rerun and answer y, or pass --yes"
)


def refusal_unless_approved(
    *,
    assume_yes: bool,
    stdin: TextIO,
    stdin_is_tty: Callable[[], bool],
    stderr: TextIO,
) -> str | None:
    """Return `None` when the run may start, else the message that explains the refusal.

    Reads one line from `stdin` only when `assume_yes` is unset and stdin is a TTY.
    The only text written is the prompt, plus a line break after an interrupt or EOF.
    """
    if assume_yes:
        return None
    if not stdin_is_tty():
        return NO_TTY_MESSAGE
    stderr.write(PROMPT)
    stderr.flush()
    try:
        answer = stdin.readline()
    except KeyboardInterrupt:
        stderr.write("\n")
        return DECLINED_MESSAGE
    if not answer:
        stderr.write("\n")
        return DECLINED_MESSAGE
    if answer.strip().lower() in AFFIRMATIVE_ANSWERS:
        return None
    return DECLINED_MESSAGE
