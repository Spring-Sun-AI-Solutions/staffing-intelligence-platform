"""
data/redis_client.py
Redis client for:
  1. Query result caching    — fast page loads on revisit
  2. AI assistant chat history — per-user session memory
  3. Nightly job status      — track last run time

Usage:
    from data.redis_client import (
        cache_set, cache_get, cache_delete,
        save_chat_history, get_chat_history, clear_chat_history,
    )

    # Cache a query result for 5 minutes
    cache_set("candidates:all", df.to_json(), ttl=300)
    cached = cache_get("candidates:all")

    # Chat history
    save_chat_history("user123", messages)
    messages = get_chat_history("user123")
"""
import json
import logging
import os
from typing import Any, Optional

from data.logger import get_logger

logger = get_logger("data.redis")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Cache TTLs (seconds)
TTL_QUERY_RESULT   = 300    # 5 minutes — candidate lists, job lists
TTL_MATCH_RESULT   = 180    # 3 minutes — ranked candidates (more dynamic)
TTL_CHAT_HISTORY   = 3600   # 1 hour — AI assistant conversation
TTL_PREDICTION     = 600    # 10 minutes — ML predictions
TTL_FORECAST       = 1800   # 30 minutes — revenue forecasts

_redis_client = None


def get_redis() -> Optional[object]:
    """
    Get Redis client. Returns None if Redis is not available
    (graceful degradation — app works without Redis, just slower).
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        client.ping()
        _redis_client = client
        logger.info("Redis connected")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis not available: {e} — caching disabled")
        return None


# ── Generic cache ─────────────────────────────────────────────────────────────

def cache_set(key: str, value: Any, ttl: int = TTL_QUERY_RESULT) -> bool:
    """
    Store a value in Redis cache.

    Args:
        key:   cache key (e.g. "candidates:all", "match:job_5")
        value: any JSON-serialisable value
        ttl:   time-to-live in seconds

    Returns:
        True if cached, False if Redis unavailable
    """
    r = get_redis()
    if r is None:
        return False
    try:
        serialised = json.dumps(value, default=str)
        r.setex(f"sip:{key}", ttl, serialised)
        logger.debug(f"Cached: {key} (TTL={ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Cache set failed for {key}: {e}")
        return False


def cache_get(key: str) -> Optional[Any]:
    """
    Retrieve a value from Redis cache.

    Returns:
        Deserialised value, or None if not cached / Redis unavailable
    """
    r = get_redis()
    if r is None:
        return None
    try:
        raw = r.get(f"sip:{key}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Cache get failed for {key}: {e}")
        return None


def cache_delete(key: str) -> bool:
    """Delete a cache key."""
    r = get_redis()
    if r is None:
        return False
    try:
        r.delete(f"sip:{key}")
        return True
    except Exception:
        return False


def cache_invalidate_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern.
    e.g. cache_invalidate_pattern("match:*") clears all match results.
    """
    r = get_redis()
    if r is None:
        return 0
    try:
        keys = r.keys(f"sip:{pattern}")
        if keys:
            r.delete(*keys)
        return len(keys)
    except Exception as e:
        logger.warning(f"Cache invalidation failed for {pattern}: {e}")
        return 0


# ── AI assistant chat history ─────────────────────────────────────────────────

def save_chat_history(session_id: str, messages: list[dict]) -> bool:
    """
    Save AI assistant conversation history for a user session.

    Args:
        session_id: Streamlit session ID or username
        messages:   list of {"role": "user"|"assistant", "content": "..."}
    """
    return cache_set(f"chat:{session_id}", messages, ttl=TTL_CHAT_HISTORY)


def get_chat_history(session_id: str) -> list[dict]:
    """
    Retrieve AI assistant conversation history.

    Returns:
        List of message dicts, or empty list if no history
    """
    cached = cache_get(f"chat:{session_id}")
    return cached if cached is not None else []


def clear_chat_history(session_id: str) -> bool:
    """Clear chat history for a session."""
    return cache_delete(f"chat:{session_id}")


def append_chat_message(session_id: str, role: str, content: str) -> list[dict]:
    """
    Append a single message to the chat history and return updated history.

    Args:
        session_id: user session identifier
        role:       "user" or "assistant"
        content:    message text
    """
    history = get_chat_history(session_id)
    history.append({"role": role, "content": content})
    # Keep last 50 messages to avoid hitting Redis size limits
    if len(history) > 50:
        history = history[-50:]
    save_chat_history(session_id, history)
    return history


# ── Match result caching ──────────────────────────────────────────────────────

def cache_match_results(job_id: int, results: list[dict]) -> bool:
    """Cache ranked candidate results for a job."""
    return cache_set(f"match:job_{job_id}", results, ttl=TTL_MATCH_RESULT)


def get_cached_match_results(job_id: int) -> Optional[list[dict]]:
    """Get cached match results for a job."""
    return cache_get(f"match:job_{job_id}")


def invalidate_match_cache(job_id: Optional[int] = None):
    """Invalidate match cache — call when candidates or jobs change."""
    if job_id:
        cache_delete(f"match:job_{job_id}")
    else:
        cache_invalidate_pattern("match:*")


# ── Nightly job tracking ──────────────────────────────────────────────────────

def set_job_last_run(job_name: str) -> bool:
    """Record that a scheduled job just ran successfully."""
    from datetime import datetime
    return cache_set(
        f"job_last_run:{job_name}",
        datetime.utcnow().isoformat(),
        ttl=86400 * 2,  # 2 days
    )


def get_job_last_run(job_name: str) -> Optional[str]:
    """Get the last run time of a scheduled job."""
    return cache_get(f"job_last_run:{job_name}")


# ── Redis health check ────────────────────────────────────────────────────────

def get_redis_info() -> dict:
    """Return Redis status info for admin dashboard."""
    r = get_redis()
    if r is None:
        return {"available": False, "reason": "Redis not reachable"}
    try:
        info = r.info()
        keys = len(r.keys("sip:*"))
        return {
            "available":       True,
            "version":         info.get("redis_version"),
            "used_memory_mb":  round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "connected_clients": info.get("connected_clients"),
            "sip_keys":        keys,
            "uptime_hours":    round(info.get("uptime_in_seconds", 0) / 3600, 1),
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}
