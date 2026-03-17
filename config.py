"""
Runtime configuration for CRUXpider.
"""

from __future__ import annotations

import os


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


HOST = os.getenv("CRUXPIDER_HOST", "0.0.0.0")
PORT = _get_int("CRUXPIDER_PORT", 5003)
SECRET_KEY = os.getenv("CRUXPIDER_SECRET_KEY", "cruxpider-dev-secret")

PYALEX_EMAIL = os.getenv("PYALEX_EMAIL", "")
PAPERSWITHCODE_API_KEY = os.getenv("PAPERSWITHCODE_API_KEY", "")
PAPERSWITHCODE_API_BASE = os.getenv(
    "PAPERSWITHCODE_API_BASE",
    "https://paperswithcode.com/api/v1/",
)

REQUEST_TIMEOUT_SECONDS = _get_float("CRUXPIDER_REQUEST_TIMEOUT", 12.0)
MAX_BATCH_SIZE = _get_int("CRUXPIDER_MAX_BATCH_SIZE", 50)
LOG_LEVEL = os.getenv("CRUXPIDER_LOG_LEVEL", "INFO")
