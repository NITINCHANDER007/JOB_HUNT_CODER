"""
Structured logging setup for AutoApply AI.
"""

import os
import logging
import structlog
from logging.handlers import RotatingFileHandler


def setup_logging():
    """Configure structlog and standard logging."""
    log_level = logging.DEBUG if os.getenv("FLASK_ENV") == "development" else logging.INFO

    # File handler
    os.makedirs("logs", exist_ok=True)
    file_handler = RotatingFileHandler(
        "logs/autoapply.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    logging.basicConfig(
        level=log_level,
        handlers=[file_handler, console_handler],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """Get a structlog logger instance."""
    return structlog.get_logger(name)
