"""
Centralized logging configuration for I AM Live Stream Co-Host.
Provides configure_logging(process_tag: str) to ensure standardized logging formats across processes.
"""

import logging
import sys


def configure_logging(process_tag: str = "MAIN", level: int = logging.INFO):
    """
    Configures standard stream logging with a process tag.
    """
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    logging.basicConfig(
        level=level,
        format=f"%(asctime)s [%(levelname)s] [{process_tag}] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def setup_logging(process_tag: str = "MAIN", level: int = logging.INFO):
    """Backward-compatible alias for configure_logging."""
    configure_logging(process_tag, level)

