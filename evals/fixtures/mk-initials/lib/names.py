"""Name formatting."""


def initials(full_name: str) -> str:
    """Upper-case initials of each word, joined with dots: 'ada lovelace' -> 'A.L.'."""
    words = [word for word in full_name.split() if word]
    if not words:
        return ""
    return "".join(word[0].upper() + "." for word in words)
