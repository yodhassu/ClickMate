"""Picks the AI brain: Ollama (local) or Gemini (cloud). Both expose the same methods:
check(), warmup(), stream_chat(messages), ask_images(prompt, images), plus .label.
Gemini also has native_pointing = True, which makes locator.py skip the grid game."""
import config
import llm
from gemini_client import GeminiClient


def make_client(provider: str = None):
    provider = (provider or config.PROVIDER).lower()
    if provider == "gemini":
        return GeminiClient()
    return llm.OllamaClient()
