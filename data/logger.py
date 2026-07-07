"""
data/logger.py
Deep structured logging for the Staffing Intelligence Platform.

Features:
- JSON structured logs (machine-readable for analysis)
- Human-readable console logs (colour-coded by level)
- Separate log files per subsystem (parser, embedder, db, scheduler)
- Request ID tracking across a full parse-embed-store pipeline
- Automatic log rotation (10MB per file, 5 backups)
- Performance log: records slow operations to logs/slow_ops.log

Usage:
    from data.logger import get_logger, log_parse_event, log_embed_event

    logger = get_logger("ml.parser")
    logger.info("Parsing resume", extra={"candidate_id": 42})

    # High-level event loggers (structured, for analytics)
    log_parse_event(candidate_id=42, file_type="pdf", skills_found=12, yoe=5.0)
    log_embed_event(entity_type="candidate", entity_id=42, dim=384, duration_ms=45)
"""
import json
import logging
import logging.handlers
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

# ── Log directory ─────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Request context (thread-local) ────────────────────────────────────────────
_local = threading.local()


def get_request_id() -> str:
    """Get or create a request ID for the current thread."""
    if not hasattr(_local, "request_id"):
        _local.request_id = str(uuid.uuid4())[:8]
    return _local.request_id


def set_request_id(request_id: str):
    """Set a specific request ID (e.g. from Streamlit session)."""
    _local.request_id = request_id


def new_request_id() -> str:
    """Start a new request context."""
    _local.request_id = str(uuid.uuid4())[:8]
    return _local.request_id


# ── JSON formatter ────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Outputs one JSON object per log line — easy to grep and analyse."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts":        datetime.utcnow().isoformat() + "Z",
            "level":     record.levelname,
            "logger":    record.name,
            "msg":       record.getMessage(),
            "request_id": get_request_id(),
        }
        # Include any extra fields passed via extra={}
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                log_obj[key] = val

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


# ── Colour console formatter ──────────────────────────────────────────────────

class ColourFormatter(logging.Formatter):
    """Human-readable coloured console output."""

    COLOURS = {
        "DEBUG":    "\033[36m",   # Cyan
        "INFO":     "\033[32m",   # Green
        "WARNING":  "\033[33m",   # Yellow
        "ERROR":    "\033[31m",   # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, "")
        rid = get_request_id()
        prefix = f"{colour}[{record.levelname[0]}]{self.RESET}"
        ts = datetime.utcnow().strftime("%H:%M:%S")
        return f"{prefix} {ts} [{rid}] {record.name}: {record.getMessage()}"


# ── Slow ops filter ───────────────────────────────────────────────────────────

class SlowOpsFilter(logging.Filter):
    """Only passes log records that indicate slow operations (> 1 second)."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage().lower()
        return "slow" in msg or "took" in msg or "timeout" in msg


# ── Logger factory ────────────────────────────────────────────────────────────

_configured_loggers: set[str] = set()
_setup_lock = threading.Lock()


def get_logger(name: str) -> logging.Logger:
    """
    Get a fully configured logger for the given subsystem name.

    Creates:
    - Console handler (coloured, INFO+)
    - JSON rotating file handler for this subsystem (DEBUG+)
    - Slow ops file handler (WARNING+, only slow ops)

    Args:
        name: dotted module name e.g. "ml.parser", "db.queries", "data.scheduler"
    """
    with _setup_lock:
        if name in _configured_loggers:
            return logging.getLogger(name)

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False  # Don't bubble up to root logger

        # 1. Console — colour, INFO and above
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(ColourFormatter())
        logger.addHandler(console)

        # 2. JSON rotating file — DEBUG and above, subsystem-specific file
        subsystem = name.split(".")[0]  # e.g. "ml" from "ml.parser"
        log_file = LOG_DIR / f"{subsystem}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

        # 3. Slow ops file — WARNING and above, only slow/timeout messages
        slow_file = LOG_DIR / "slow_ops.log"
        slow_handler = logging.handlers.RotatingFileHandler(
            slow_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        slow_handler.setLevel(logging.WARNING)
        slow_handler.addFilter(SlowOpsFilter())
        slow_handler.setFormatter(JSONFormatter())
        logger.addHandler(slow_handler)

        _configured_loggers.add(name)
        return logger


def setup_root_logging(level: str = "INFO"):
    """
    Configure root logger. Call once at app startup (in app.py).
    Suppresses noisy third-party loggers.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger → app.log (catches anything not handled by subsystem loggers)
    root = logging.getLogger()
    root.setLevel(log_level)

    if not root.handlers:
        app_file = LOG_DIR / "app.log"
        handler = logging.handlers.RotatingFileHandler(
            app_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(JSONFormatter())
        root.addHandler(handler)

    # Suppress noisy third-party logs
    for noisy in [
        "urllib3", "httpx", "httpcore", "sentence_transformers",
        "transformers", "torch", "PIL", "pdfminer",
        "alembic", "sqlalchemy.engine", "watchdog",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── Structured event loggers ──────────────────────────────────────────────────

_event_logger = None


def _get_event_logger() -> logging.Logger:
    global _event_logger
    if _event_logger is None:
        _event_logger = get_logger("events")
    return _event_logger


def log_parse_event(
    candidate_id: int,
    file_type: str,
    skills_found: int,
    yoe: float,
    visa_status: str,
    duration_ms: float,
    success: bool = True,
    error: str = None,
):
    """Log a resume parse event for analytics."""
    _get_event_logger().info(
        "resume_parsed",
        extra={
            "event":        "resume_parsed",
            "candidate_id": candidate_id,
            "file_type":    file_type,
            "skills_found": skills_found,
            "yoe":          yoe,
            "visa_status":  visa_status,
            "duration_ms":  round(duration_ms, 2),
            "success":      success,
            "error":        error,
        },
    )


def log_embed_event(
    entity_type: str,
    entity_id: int,
    dim: int,
    duration_ms: float,
    success: bool = True,
):
    """Log an embedding generation event."""
    _get_event_logger().info(
        "embedding_generated",
        extra={
            "event":       "embedding_generated",
            "entity_type": entity_type,
            "entity_id":   entity_id,
            "dim":         dim,
            "duration_ms": round(duration_ms, 2),
            "success":     success,
        },
    )


def log_db_query_event(
    query_name: str,
    duration_ms: float,
    row_count: int = None,
    error: str = None,
):
    """Log a database query event."""
    level = logging.WARNING if duration_ms > 500 else logging.DEBUG
    _get_event_logger().log(
        level,
        "db_query",
        extra={
            "event":       "db_query",
            "query_name":  query_name,
            "duration_ms": round(duration_ms, 2),
            "row_count":   row_count,
            "slow":        duration_ms > 500,
            "error":       error,
        },
    )


def log_prediction_event(
    model_name: str,
    entity_type: str,
    entity_id: int,
    score: float,
    duration_ms: float,
):
    """Log an ML prediction event (Sprint 4+)."""
    _get_event_logger().info(
        "prediction_made",
        extra={
            "event":       "prediction_made",
            "model_name":  model_name,
            "entity_type": entity_type,
            "entity_id":   entity_id,
            "score":       round(score, 4),
            "duration_ms": round(duration_ms, 2),
        },
    )


# ── Log reader (for admin dashboard) ─────────────────────────────────────────

def tail_log(log_name: str = "app", lines: int = 100) -> list[dict]:
    """
    Read the last N lines from a log file and return as list of dicts.
    Used by the admin page to show recent log entries.

    Args:
        log_name: "app", "ml", "data", "db", "events", "slow_ops"
        lines: number of lines to return

    Returns:
        List of parsed JSON log objects (most recent last)
    """
    log_file = LOG_DIR / f"{log_name}.log"
    if not log_file.exists():
        return []

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        result = []
        for line in all_lines[-lines:]:
            line = line.strip()
            if line:
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    result.append({"msg": line, "level": "UNKNOWN"})
        return result
    except Exception as e:
        return [{"msg": f"Error reading log: {e}", "level": "ERROR"}]


def get_log_stats() -> dict:
    """Return log file sizes and line counts for admin dashboard."""
    stats = {}
    for log_file in LOG_DIR.glob("*.log"):
        try:
            size_kb = log_file.stat().st_size / 1024
            with open(log_file, "r", encoding="utf-8") as f:
                lines = sum(1 for _ in f)
            stats[log_file.stem] = {
                "size_kb": round(size_kb, 1),
                "lines":   lines,
                "path":    str(log_file),
            }
        except Exception:
            pass
    return stats
