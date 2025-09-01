from __future__ import annotations
import logging
from pathlib import Path
import sys

def setup_logger(name: str = "pipeline", logs_dir: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)

    # file handler
    if logs_dir:
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(logs_dir / "pipeline.log", encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(fh)
        except Exception as e:
            logger.warning(f"Could not create log file in {logs_dir}: {e}")

    return logger
