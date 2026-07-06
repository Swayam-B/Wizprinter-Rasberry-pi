"""
Structured rotating-file logger for WizPrinter.

Import once from main.py before any other wizprinter module:

    from wizprinter.logger import setup_logging
    setup_logging()

All modules then use:

    import logging
    logger = logging.getLogger(__name__)
"""

import logging
import logging.handlers
import os


def setup_logging() -> None:
    """Configure root logger: rotating file + stderr stream."""
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_dir = os.environ.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    max_bytes = int(os.environ.get("LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # 5 MB
    backup_count = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level)

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "wizprinter.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler (stderr) — useful during development / SSH sessions
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.WARNING)   # only warnings+ to console
    root.addHandler(sh)

    # Suppress noisy third-party loggers
    logging.getLogger("kivy").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Logging initialised (level=%s)", log_level_name)
