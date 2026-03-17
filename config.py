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
OPENALEX_API_BASE = os.getenv("OPENALEX_API_BASE", "https://api.openalex.org/works")
SEMANTIC_SCHOLAR_API_BASE = os.getenv(
    "SEMANTIC_SCHOLAR_API_BASE",
    "https://api.semanticscholar.org/graph/v1",
)
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
CROSSREF_API_BASE = os.getenv("CROSSREF_API_BASE", "https://api.crossref.org")
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", PYALEX_EMAIL)
GITHUB_API_BASE = os.getenv("GITHUB_API_BASE", "https://api.github.com")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

REQUEST_TIMEOUT_SECONDS = _get_float("CRUXPIDER_REQUEST_TIMEOUT", 12.0)
MAX_BATCH_SIZE = _get_int("CRUXPIDER_MAX_BATCH_SIZE", 50)
RESULT_CACHE_TTL_SECONDS = _get_int("CRUXPIDER_RESULT_CACHE_TTL", 900)
LOG_LEVEL = os.getenv("CRUXPIDER_LOG_LEVEL", "INFO")
