"""
utils/logger.py — TelescopeAI Logging Configuration

Provides a unified logging setup for the entire application.
All modules should use get_logger(__name__) instead of print().

Log levels:
    DEBUG    — every frame, PID value, rate sent (file only — too noisy for console)
    INFO     — system state changes (connected, locked, lost, slewing)
    WARNING  — unexpected values, timeouts, degraded operation
    ERROR    — failures that need attention (camera not found, ASCOM error)
    CRITICAL — fatal errors that prevent operation

Usage:
    # In main.py / calibration.py (once at startup):
    from utils.logger import setup_logging
    setup_logging(cfg['logging'])

    # In every other module:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("[CONNECT] Telescope connected")
    logger.debug("[PID] Az rate=%.3f Alt rate=%.3f", rate_az, rate_alt)
    logger.error("[CAMERA] Failed to open index %d", index)

Log format:
    2026-03-18 21:30:15  INFO      hardware.ascom  — [CONNECT] Telescope connected
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

# ── format ───────────────────────────────────────────────────────────────────

_LOG_FORMAT  = "%(asctime)s  %(levelname)-8s  %(name)-20s — %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LEVEL_MAP = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "ERROR":    logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


# ── public API ────────────────────────────────────────────────────────────────

def setup_logging(logging_cfg: Optional[dict] = None) -> None:
    """
    Configure the root logger.  Call once at application startup.

    Args:
        logging_cfg: the 'logging' section from config.yaml, e.g.:
            {
                'level':      'INFO',   # console log level
                'file':       'telescope.log',  # None to disable file logging
                'file_level': 'DEBUG',  # file log level (usually more verbose)
            }
            Pass None (or omit) to use safe defaults (INFO to console only).

    Side effects:
        - Adds a StreamHandler (stderr) at the configured level
        - Optionally adds a RotatingFileHandler (max 5 MB × 3 backups)
        - Suppresses overly verbose library loggers (skyfield, PIL, etc.)
    """
    cfg = logging_cfg or {}

    console_level = _LEVEL_MAP.get(str(cfg.get("level", "INFO")).upper(), logging.INFO)
    log_file      = cfg.get("file")          # None = no file logging
    file_level    = _LEVEL_MAP.get(str(cfg.get("file_level", "DEBUG")).upper(), logging.DEBUG)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # root catches everything; handlers filter

    # ── console handler (stderr) ──────────────────────────────────────────
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # ── rotating file handler ─────────────────────────────────────────────
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB per file
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        logging.getLogger(__name__).info(
            "[LOGGER] File logging enabled → %s (level=%s)", log_file, cfg.get("file_level", "DEBUG")
        )

    # ── quiet noisy third-party loggers ───────────────────────────────────
    for noisy in ("skyfield", "PIL", "matplotlib", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger for a module.

    Args:
        name: Use __name__ — Python will automatically use the module path
              (e.g. 'hardware.ascom_driver', 'core.tracker')

    Returns:
        logging.Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("[CONNECT] OK")
    """
    return logging.getLogger(name)
