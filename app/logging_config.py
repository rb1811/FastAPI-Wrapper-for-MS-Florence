import logging
import sys
import os
import structlog
import functools
import logfire
from structlog.types import Processor

# Constants
service_name = os.environ.get("SERVICE_NAME", "florence-ai")
# Request: If dev mode is set to false, do NOT send logs to logfire. If set to true, send it.
# Logic: LOGFIRE_ENABLED is True only when DEV_MODE is "true"
DEV_MODE_STR = os.environ.get("DEV_MODE", "True").lower()
LOGFIRE_ENABLED = DEV_MODE_STR == "false"
print(f"Logfire status: {LOGFIRE_ENABLED}")

def flush_after(func):
    """Decorator to ensure stdout is flushed after a log event."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        sys.stdout.flush()
        try:
            os.fsync(sys.stdout.fileno())
        except Exception:
            pass
        return result
    return wrapper

def setup_logging():
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level_str)
    
    # Initialize Logfire ONLY if LOGFIRE_ENABLED is true
    if LOGFIRE_ENABLED:
        logfire.configure(service_name=service_name)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # Add the Logfire processor if enabled
    if LOGFIRE_ENABLED:
        shared_processors.append(logfire.StructlogProcessor())

    shared_processors.extend([
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ],
            additional_ignores=["logging", "structlog"],
        ),
    ])

    # Console for human reading, JSON for machine parsing (Production)
    if DEV_MODE_STR == "true":
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]
    else:
        processors = shared_processors + [structlog.processors.JSONRenderer()]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Initialize once on module import
setup_logging()

class Logger:
    def __init__(self, name: str):
        self._logger = structlog.get_logger(name)

    @flush_after
    def debug(self, message: str, **kwargs):
        self._logger.debug(message, **{"stacklevel": 2}, **kwargs)

    @flush_after
    def info(self, message: str, **kwargs):
        self._logger.info(message, **{"stacklevel": 2}, **kwargs)

    @flush_after
    def warning(self, message: str, **kwargs):
        self._logger.warning(message, **{"stacklevel": 2}, **kwargs)

    @flush_after
    def error(self, message: str, **kwargs):
        self._logger.error(message, **{"stacklevel": 2}, **kwargs)

    @flush_after
    def exception(self, message: str, **kwargs):
        self._logger.exception(message, **{"stacklevel": 2}, **kwargs)

def get_logger(name: str) -> Logger:
    return Logger(name)