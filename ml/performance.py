"""
ml/performance.py
Performance tuning utilities for the NLP pipeline.

Optimisations applied:
1. spaCy model caching — load once, reuse across all requests
2. Embedding model caching — load once into memory
3. Batch processing with configurable batch sizes
4. Text truncation before embedding to stay within model token limits
5. Timer decorators for profiling slow functions
6. LRU cache for repeated skill normalisations

Usage:
    from ml.performance import timed, get_pipeline_stats, warm_up_models

    @timed("parse_resume")
    def my_function(): ...

    warm_up_models()         # pre-load models at app startup
    stats = get_pipeline_stats()  # get timing stats
"""
import time
import functools
import logging
import threading
from collections import defaultdict
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ── Global stats store (thread-safe) ─────────────────────────────────────────
_stats_lock = threading.Lock()
_stats: dict[str, list[float]] = defaultdict(list)


def timed(operation_name: str):
    """
    Decorator that measures and records execution time.

    Usage:
        @timed("embed_text")
        def embed_text(text): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                with _stats_lock:
                    _stats[operation_name].append(elapsed)
                if elapsed > 1.0:
                    logger.warning(f"[perf] {operation_name} took {elapsed:.2f}s (slow)")
                else:
                    logger.debug(f"[perf] {operation_name} took {elapsed*1000:.1f}ms")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                logger.error(f"[perf] {operation_name} FAILED after {elapsed:.2f}s: {e}")
                raise
        return wrapper
    return decorator


def get_pipeline_stats() -> dict:
    """
    Return timing statistics for all measured operations.

    Returns dict like:
        {
          "embed_text": {"calls": 42, "avg_ms": 12.3, "max_ms": 45.1, "total_s": 0.52},
          ...
        }
    """
    with _stats_lock:
        result = {}
        for name, times in _stats.items():
            if not times:
                continue
            result[name] = {
                "calls":    len(times),
                "avg_ms":   round(sum(times) / len(times) * 1000, 2),
                "min_ms":   round(min(times) * 1000, 2),
                "max_ms":   round(max(times) * 1000, 2),
                "total_s":  round(sum(times), 3),
                "p95_ms":   round(sorted(times)[int(len(times) * 0.95)] * 1000, 2)
                            if len(times) >= 20 else None,
            }
        return result


def reset_stats():
    """Clear all collected timing stats."""
    with _stats_lock:
        _stats.clear()


# ── Model warm-up ─────────────────────────────────────────────────────────────

def warm_up_models():
    """
    Pre-load spaCy and sentence-transformer models at app startup.
    Prevents the first user request from being slow due to model loading.

    Call this once from app.py after auth setup.
    """
    logger.info("[perf] Warming up NLP models...")
    start = time.perf_counter()

    try:
        # Warm up spaCy
        from ml.parser import _get_nlp
        nlp = _get_nlp()
        _ = nlp("warm up text")
        logger.info("[perf] spaCy model ready")
    except Exception as e:
        logger.warning(f"[perf] spaCy warm-up failed: {e}")

    try:
        # Warm up sentence-transformers
        from ml.embedder import embed_text
        _ = embed_text("warm up embedding")
        logger.info("[perf] Embedding model ready")
    except Exception as e:
        logger.warning(f"[perf] Embedding warm-up failed: {e}")

    elapsed = time.perf_counter() - start
    logger.info(f"[perf] Models warmed up in {elapsed:.2f}s")
    return elapsed


# ── Batch size recommendations ────────────────────────────────────────────────

def recommended_batch_size() -> int:
    """
    Recommend an embedding batch size based on available RAM.
    Conservative defaults — safe for 16GB machines.
    """
    try:
        import psutil
        available_gb = psutil.virtual_memory().available / (1024 ** 3)
        if available_gb >= 16:
            return 64
        elif available_gb >= 8:
            return 32
        else:
            return 16
    except ImportError:
        return 32  # safe default without psutil


# ── Text truncation ───────────────────────────────────────────────────────────

def truncate_for_embedding(text: str, max_chars: int = 4000) -> str:
    """
    Truncate text to stay within model token limits.
    Tries to truncate at a sentence boundary.
    """
    if len(text) <= max_chars:
        return text
    # Try to cut at last full stop within limit
    cut = text[:max_chars].rfind(".")
    if cut > max_chars * 0.8:
        return text[:cut + 1]
    return text[:max_chars]


# ── Cached skill normalisation ────────────────────────────────────────────────

@functools.lru_cache(maxsize=512)
def cached_normalise_skill(raw: str) -> str:
    """LRU-cached version of normalise_skill — avoids repeated dict lookups."""
    from ml.parser import normalise_skill
    return normalise_skill(raw)
