"""Concise, Jenkins-friendly logging configuration shared by all modules."""
import logging
import sys

_CONFIGURED = False


def configure_logging(level=logging.INFO):
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    _CONFIGURED = True


def get_logger(name):
    configure_logging()
    return logging.getLogger(name)
