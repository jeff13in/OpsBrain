"""Role-specific chat clients for Groq and OpenAI-compatible local endpoints.

Configuration is read at construction time; importing this module needs no
credentials, database settings, or network access. Gemini embeddings are separate.
"""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlsplit

from langchain_openai import ChatOpenAI

ChatRole = Literal["router", "answer", "synth"]
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODELS = {
    "router": "openai/gpt-oss-20b",
    "answer": "openai/gpt-oss-120b",
    # Verified against https://console.groq.com/docs/models on 2026-10-10.
    "synth": "qwen/qwen3.8-27b",
}
TIMEOUTS = {"router": 10.0, "answer": 45.0, "synth": 20.0}
MAX_TOKENS = {"router": 1024, "answer": 2048, "synth": 1536}


class ChatConfigurationError(ValueError):
    """An invalid role or missing chat setting; messages contain no secrets."""


def get_chat_model(role: ChatRole) -> ChatOpenAI:
    """Construct a client with no automatic retries, including HTTP 429 retries.

    Ollama accepts an arbitrary nonempty LLM_API_KEY (e.g. ``ollama``).
    Models must be set to locally installed names when using that endpoint.
    """
    if role not in DEFAULT_MODELS:
        raise ChatConfigurationError("Chat role must be router, answer, or synth.")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key or api_key == "...":
        raise ChatConfigurationError("LLM_API_KEY is required for chat generation.")
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    try:
        parsed = urlsplit(base_url)
        valid_url = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
        valid_url = valid_url and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
        _ = parsed.port
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ChatConfigurationError("LLM_BASE_URL must be an HTTP(S) endpoint without credentials or query parameters.")
    variable = f"LLM_MODEL_{role.upper()}"
    model = os.getenv(variable, DEFAULT_MODELS[role]).strip()
    if not model:
        raise ChatConfigurationError(f"{variable} must not be blank.")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        timeout=TIMEOUTS[role],
        max_tokens=MAX_TOKENS[role],
        max_retries=0,
        use_responses_api=False,
    )
