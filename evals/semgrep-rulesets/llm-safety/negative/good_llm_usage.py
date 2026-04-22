"""Negative fixture — should produce zero matches."""
import os
from anthropic import Anthropic


def chat_with_claude(user_input: str):
    # API key from env
    c = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Structured messages — no string concatenation
    return c.messages.create(
        model="claude-opus-4-7",
        system="You are an assistant.",
        messages=[{"role": "user", "content": user_input}],
    )
