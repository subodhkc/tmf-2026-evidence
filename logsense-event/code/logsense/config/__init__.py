"""
LogSense Configuration Module
"""

from .constants import (
    ALLOWED_EXTENSIONS,
    CONFIDENCE_THRESHOLD_ALTERNATE,
    CONFIDENCE_THRESHOLD_PRIMARY,
    MAX_FILE_SIZE_MB,
)
from .settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
    "MAX_FILE_SIZE_MB",
    "ALLOWED_EXTENSIONS",
    "CONFIDENCE_THRESHOLD_PRIMARY",
    "CONFIDENCE_THRESHOLD_ALTERNATE",
]
