"""
ml/llm_client.py
Ollama LLM client — wraps the local Llama 3 model.

Features:
- Streaming responses (for chat UI)
- Retry logic with exponential backoff
- Prompt templating
- Token usage tracking
- Health check

Usage:
    from ml.llm_client import chat, stream_chat, health_check

    # Single response
    response = chat("What skills does a Python developer need?")

    # Streaming (for Streamlit chat UI)
    for chunk in stream_chat("Summarise this JD: ...", system="You are a recruiter"):
        print(chunk, end="", flush=True)
"""
import logging
import os
import time
from typing import Generator, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv
load_dotenv()
from data.logger import get_logger

logger = get_logger("ml.llm")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
TIMEOUT         = 120  # seconds — LLM can be slow on first token


# ── Health check ──────────────────────────────────────────────────────────────

def health_check() -> dict:
    """Check if Ollama is running and the model is available."""
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models = [m["name"] for m in response.json().get("models", [])]
            model_available = any(OLLAMA_MODEL in m for m in models)
            return {
                "available":       True,
                "models":          models,
                "model_ready":     model_available,
                "model":           OLLAMA_MODEL,
            }
    except Exception as e:
        logger.warning(f"Ollama health check failed: {e}")
    return {"available": False, "model_ready": False, "model": OLLAMA_MODEL}


def pull_model() -> bool:
    """Pull the configured model if not already available."""
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": OLLAMA_MODEL, "stream": False},
            timeout=300,
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Model pull failed: {e}")
        return False


# ── Core chat function ────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
def chat(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """
    Send a prompt to Ollama and return the full response.

    Args:
        prompt:      user message
        system:      system prompt (sets LLM persona)
        temperature: 0.0 = deterministic, 1.0 = creative (default 0.3 for structured output)
        max_tokens:  maximum tokens in response

    Returns:
        Full response string
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    start = time.perf_counter()
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model":    OLLAMA_MODEL,
                "messages": messages,
                "stream":   False,
                "options":  {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
        content = result["message"]["content"]
        elapsed = time.perf_counter() - start
        logger.info(f"LLM response: {len(content)} chars in {elapsed:.1f}s")
        return content

    except httpx.TimeoutException:
        logger.error("Ollama timed out — model may still be loading")
        raise
    except Exception as e:
        logger.error(f"LLM chat failed: {e}")
        raise


def stream_chat(
    prompt: str,
    system: Optional[str] = None,
    history: Optional[list[dict]] = None,
    temperature: float = 0.5,
) -> Generator[str, None, None]:
    """
    Stream a response from Ollama token by token.
    Used by the Streamlit chat UI with st.write_stream().

    Args:
        prompt:      user message
        system:      system prompt
        history:     list of prior messages [{"role": ..., "content": ...}]
        temperature: creativity (0.0–1.0)

    Yields:
        String chunks as they arrive
    """
    import json as _json

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    try:
        with httpx.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model":    OLLAMA_MODEL,
                "messages": messages,
                "stream":   True,
                "options":  {"temperature": temperature},
            },
            timeout=TIMEOUT,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = _json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
                    except _json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error(f"LLM streaming failed: {e}")
        yield f"\n\n❌ LLM error: {e}"


def chat_with_history(
    messages: list[dict],
    system: Optional[str] = None,
    temperature: float = 0.5,
) -> str:
    """
    Multi-turn chat with full conversation history.
    Used by the RAG assistant pipeline.
    """
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model":    OLLAMA_MODEL,
            "messages": all_messages,
            "stream":   False,
            "options":  {"temperature": temperature},
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]
