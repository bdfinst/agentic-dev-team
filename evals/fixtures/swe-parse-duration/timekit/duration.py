"""Duration helpers."""

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE


def format_duration(seconds: int) -> str:
    """Format a number of seconds as `<h>h<m>m<s>s`, omitting zero parts."""
    if seconds < 0:
        raise ValueError("seconds must not be negative")
    hours, rest = divmod(seconds, SECONDS_PER_HOUR)
    minutes, secs = divmod(rest, SECONDS_PER_MINUTE)
    parts = [f"{value}{unit}" for value, unit in ((hours, "h"), (minutes, "m"), (secs, "s")) if value]
    return "".join(parts) or "0s"
