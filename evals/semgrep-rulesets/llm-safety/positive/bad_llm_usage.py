"""Positive fixture for llm-safety rules."""
import openai
from anthropic import Anthropic


# Expected match: llm-safety.hardcoded-api-key (ERROR)
openai.api_key = "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def chat_with_claude(user_input):
    # Expected match: llm-safety.hardcoded-api-key (ERROR)
    c = Anthropic(api_key="sk-ant-api03-yyyyyyyyyyyyyyyyyyyyyyyyyyyy")

    # Expected match: llm-safety.prompt-template-string-injection (WARNING)
    prompt = f"You are an assistant. User asked: {user_input}"
    return c.messages.create(model="claude-opus-4-7", messages=[{"role": "user", "content": prompt}])
