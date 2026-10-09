"""
Canonical Event Models
Pydantic models for normalized log events used across all engines.
"""

from datetime import datetime
from enum import Enum
from typing import Any, cast

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    """Log severity levels."""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"
    UNKNOWN = "UNKNOWN"


class LogType(str, Enum):
    """Log type classification."""
    BACKEND_APP = "backend_app"
    API_GATEWAY = "api_gateway"
    DATABASE = "database"
    BUILD_DEPLOY = "build_deploy"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    MESSAGE_QUEUE = "message_queue"
    CACHE = "cache"
    TEST_EXECUTION = "test_execution"
    UNKNOWN = "unknown"


class EvidenceLine(BaseModel):
    """Reference to a specific line in a log file."""

    file_name: str = Field(..., description="Source file name")
    line_number: int = Field(..., ge=1, description="1-indexed line number")
    content: str = Field(..., description="Line content (may be truncated)")

    def __str__(self) -> str:
        return f"{self.file_name}:{self.line_number}"


class CanonicalEvent(BaseModel):
    """
    Canonical event schema for normalized log events.
    All log types are parsed into this common format.
    """

    id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(..., description="Event timestamp in UTC")
    source: str = Field(..., description="Source file name")
    line_number: int = Field(..., ge=1, description="Original line number")

    severity: Severity = Field(default=Severity.UNKNOWN, description="Log severity")
    component: str | None = Field(default=None, description="Component/service name")
    event_type: str | None = Field(default=None, description="Event type classification")
    message: str = Field(..., description="Log message content")

    tags: list[str] = Field(default_factory=list, description="Event tags")
    correlation_ids: dict[str, str] = Field(
        default_factory=dict,
        description="Correlation IDs (request_id, session_id, etc.)"
    )

    raw_line: str = Field(..., description="Original raw log line")
    log_type: LogType = Field(default=LogType.UNKNOWN, description="Detected log type")

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata extracted from the log"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """Ensure timestamp is timezone-aware UTC."""
        if isinstance(v, str):
            from dateutil import parser
            v = parser.parse(v)
        if v.tzinfo is None:
            from datetime import timezone
            v = v.replace(tzinfo=timezone.utc)
        return cast(datetime, v)

    model_config = {"frozen": True}


class ParsedFile(BaseModel):
    """Result of parsing a single log file."""

    file_name: str = Field(..., description="Original file name")
    file_hash: str = Field(..., description="SHA-256 hash of file content")
    log_type: LogType = Field(..., description="Detected log type")

    events: list[CanonicalEvent] = Field(default_factory=list, description="Parsed events")
    total_lines: int = Field(..., ge=0, description="Total lines in file")
    parsed_lines: int = Field(..., ge=0, description="Successfully parsed lines")
    failed_lines: int = Field(..., ge=0, description="Failed to parse lines")

    time_range_start: datetime | None = Field(default=None, description="Earliest event time")
    time_range_end: datetime | None = Field(default=None, description="Latest event time")

    @property
    def parse_success_rate(self) -> float:
        """Calculate parse success rate."""
        if self.total_lines == 0:
            return 0.0
        return self.parsed_lines / self.total_lines

    @property
    def is_degraded(self) -> bool:
        """Check if parsing is degraded (>30% failures)."""
        return self.parse_success_rate < 0.7


class IngestionResult(BaseModel):
    """Result of ingesting files for analysis."""

    analysis_id: str = Field(..., description="Unique analysis identifier (hash-based)")
    input_hash: str = Field(..., description="Combined hash of all inputs")

    files: list[ParsedFile] = Field(default_factory=list, description="Parsed files")
    total_events: int = Field(default=0, description="Total events across all files")

    log_type_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Count of files by log type"
    )

    is_degraded: bool = Field(default=False, description="Whether analysis is degraded")
    degradation_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons for degradation"
    )

    processing_time_ms: int = Field(default=0, description="Processing time in milliseconds")
