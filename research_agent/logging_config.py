"""Local file + console logging for the research agent."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from research_agent.config import settings

_CONFIGURED = False


def setup_logging() -> logging.Logger:
    """Configure and return the ``research_agent`` logger.

    - Console handler at INFO level
    - Rotating file handler at DEBUG level under ``settings.log_dir``
    """
    global _CONFIGURED
    logger = logging.getLogger("research_agent")

    if _CONFIGURED:
        return logger

    logger.setLevel(settings.log_level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console -----------------------------------------------------------
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File --------------------------------------------------------------
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fh = logging.FileHandler(log_dir / f"run_{ts}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    _CONFIGURED = True
    return logger
