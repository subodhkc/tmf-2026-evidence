"""
LogSense RCA Engine
A production-grade Root Cause Analysis engine for log analysis.

Version: 2.0.0rc1
"""

__version__ = "2.0.0rc1"
__author__ = "LogSense Team"

from typing import Final

# Schema version for RCA outputs
RCA_SCHEMA_VERSION: Final[str] = "1.0"

# Engine identifiers
ENGINE_BACKEND_APP: Final[str] = "backend_app"
ENGINE_API_GATEWAY: Final[str] = "api_gateway"
ENGINE_DATABASE: Final[str] = "database"
