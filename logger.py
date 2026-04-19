"""
Logging setup - file + console output.
"""

import logging
import os

LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "lab_orchestrator.log")

_logger = None


def get_logger():
    """Get or create the shared logger."""
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger("lab_orchestrator")
    _logger.setLevel(logging.DEBUG)

    # File handler - detailed
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _logger.addHandler(fh)

    # Console handler - info and above only
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("  %(message)s"))
    _logger.addHandler(ch)

    return _logger
