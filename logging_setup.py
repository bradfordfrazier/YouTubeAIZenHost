"""
Unified Logging Configuration for AI Live Stream Host ("I AM").
Provides a single, structured logging formatter and handler across all modules and processes.
"""

import logging
import sys


class CustomFormatter(logging.Formatter):
    """
    Custom log formatter formatting log records with timestamp, level, module tag, and message:
    Example: 12:34:56 [INFO] [AI-BRAIN] Received viewer query...
    """

    def format(self, record: logging.LogRecord) -> str:
        tag = record.name.upper()
        if not tag.startswith("[") and not tag.endswith("]"):
            tag = f"[{tag}]"
        # Avoid duplicate tags if message already has a tag
        orig_msg = record.getMessage()
        time_str = self.formatTime(record, self.datefmt or "%H:%M:%S")
        level_str = record.levelname
        return f"{time_str} [{level_str}] {tag} {orig_msg}"


def setup_logging(level: int = logging.INFO, log_file: str = None) -> None:
    """
    Initializes global logging configuration once for the entire application.
    """
    # Ensure Windows console supports emojis and unicode cleanly
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on re-entry
    if root.handlers:
        for h in list(root.handlers):
            root.removeHandler(h)

    formatter = CustomFormatter(datefmt="%H:%M:%S")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
