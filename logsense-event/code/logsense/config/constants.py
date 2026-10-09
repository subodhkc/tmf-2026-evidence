"""
LogSense Constants
Immutable configuration values used across the application.
"""

from typing import Final

# ============================================================
# FILE HANDLING
# ============================================================

MAX_FILE_SIZE_MB: Final[int] = 25
MAX_FILE_SIZE_BYTES: Final[int] = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".log",
    ".txt",
    ".zip",
})

ALLOWED_CONTENT_TYPES: Final[frozenset[str]] = frozenset({
    "text/plain",
    "text/log",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
})

# ============================================================
# LOG TYPE CLASSIFICATION
# ============================================================

LOG_TYPE_BACKEND_APP: Final[str] = "backend_app"
LOG_TYPE_API_GATEWAY: Final[str] = "api_gateway"
LOG_TYPE_DATABASE: Final[str] = "database"
LOG_TYPE_UNKNOWN: Final[str] = "unknown"

# ============================================================
# CONFIDENCE SCORING
# ============================================================

CONFIDENCE_MIN: Final[int] = 0
CONFIDENCE_MAX: Final[int] = 100
CONFIDENCE_THRESHOLD_PRIMARY: Final[int] = 70
CONFIDENCE_THRESHOLD_ALTERNATE: Final[int] = 40
CONFIDENCE_THRESHOLD_INSUFFICIENT: Final[int] = 50

# ============================================================
# CAUSAL ROLES
# ============================================================

CAUSAL_ROLE_PRIMARY: Final[str] = "primary"
CAUSAL_ROLE_CONTRIBUTING: Final[str] = "contributing"
CAUSAL_ROLE_SYMPTOM: Final[str] = "symptom"

# ============================================================
# ANALYSIS STATUS
# ============================================================

STATUS_QUEUED: Final[str] = "queued"
STATUS_PROCESSING: Final[str] = "processing"
STATUS_COMPLETE: Final[str] = "complete"
STATUS_FAILED: Final[str] = "failed"
STATUS_DEGRADED: Final[str] = "degraded"
STATUS_INSUFFICIENT_SIGNAL: Final[str] = "insufficient_signal"

# ============================================================
# ERROR CODES
# ============================================================

class ErrorCode:
    """Standardized error codes."""

    # Client errors (E.REQ.xxx)
    INVALID_CONTENT_TYPE = "E.REQ.001"
    FILE_TOO_LARGE = "E.REQ.002"
    INVALID_FILE_TYPE = "E.REQ.003"
    MISSING_REQUIRED_FIELD = "E.REQ.004"
    INVALID_ANALYSIS_ID = "E.REQ.005"

    # Server errors (E.SRV.xxx)
    PROCESSING_FAILED = "E.SRV.001"
    ANALYSIS_TIMEOUT = "E.SRV.002"
    STORAGE_ERROR = "E.SRV.003"
    INTERNAL_ERROR = "E.SRV.004"

    # Security errors (E.SEC.xxx)
    UNAUTHORIZED = "E.SEC.001"
    RATE_LIMIT_EXCEEDED = "E.SEC.002"
    QUOTA_EXCEEDED = "E.SEC.003"

    # Analysis errors (E.RCA.xxx)
    INSUFFICIENT_SIGNAL = "E.RCA.001"
    PARSE_FAILED = "E.RCA.002"
    NO_LOGS_PROVIDED = "E.RCA.003"
    UNKNOWN_LOG_TYPE = "E.RCA.004"

# ============================================================
# SEVERITY LEVELS
# ============================================================

SEVERITY_CRITICAL: Final[str] = "CRITICAL"
SEVERITY_HIGH: Final[str] = "HIGH"
SEVERITY_MEDIUM: Final[str] = "MEDIUM"
SEVERITY_LOW: Final[str] = "LOW"
SEVERITY_INFO: Final[str] = "INFO"

SEVERITY_ORDER: Final[dict] = {
    SEVERITY_CRITICAL: 5,
    SEVERITY_HIGH: 4,
    SEVERITY_MEDIUM: 3,
    SEVERITY_LOW: 2,
    SEVERITY_INFO: 1,
}

# ============================================================
# TIMELINE PHASES
# ============================================================

PHASE_STARTUP: Final[str] = "startup"
PHASE_INITIALIZATION: Final[str] = "initialization"
PHASE_NORMAL: Final[str] = "normal"
PHASE_FIRST_ANOMALY: Final[str] = "first_anomaly"
PHASE_CASCADE: Final[str] = "cascade"
PHASE_FAILURE: Final[str] = "failure"
PHASE_STABILIZATION: Final[str] = "stabilization"
PHASE_SHUTDOWN: Final[str] = "shutdown"

# ============================================================
# SCHEMA VERSIONS
# ============================================================

RCA_SCHEMA_VERSION: Final[str] = "1.0"
RULE_PACK_VERSION: Final[str] = "1.0.0"

# ============================================================
# RATE LIMITING
# ============================================================

DEFAULT_RATE_LIMIT_REQUESTS: Final[int] = 100
DEFAULT_RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60

# ============================================================
# TENANT QUOTAS
# ============================================================

QUOTA_TIER_FREE: Final[str] = "free"
QUOTA_TIER_PRO: Final[str] = "pro"
QUOTA_TIER_ENTERPRISE: Final[str] = "enterprise"

QUOTA_LIMITS: Final[dict] = {
    QUOTA_TIER_FREE: {
        "max_file_size_mb": 5,
        "max_files_per_analysis": 3,
        "max_analyses_per_day": 10,
        "max_concurrent_analyses": 1,
        "retention_days": 7,
    },
    QUOTA_TIER_PRO: {
        "max_file_size_mb": 25,
        "max_files_per_analysis": 10,
        "max_analyses_per_day": 100,
        "max_concurrent_analyses": 5,
        "retention_days": 30,
    },
    QUOTA_TIER_ENTERPRISE: {
        "max_file_size_mb": 100,
        "max_files_per_analysis": 50,
        "max_analyses_per_day": 1000,
        "max_concurrent_analyses": 20,
        "retention_days": 365,
    },
}
