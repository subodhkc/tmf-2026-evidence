"""
Parse Module
Pluggable log parsers that extract canonical events from normalized lines.
"""

import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from logsense.models.events import (
    CanonicalEvent,
    LogType,
    ParsedFile,
    Severity,
)
from logsense.pipeline.ingest import IngestedFile
from logsense.pipeline.normalize import NormalizationResult, NormalizedLine

SEVERITY_PATTERNS = {
    Severity.CRITICAL: re.compile(r'\b(CRITICAL|FATAL|PANIC|EMERGENCY)\b', re.I),
    Severity.ERROR: re.compile(r'\b(ERROR|ERR|FAIL|FAILED|FAILURE)\b', re.I),
    Severity.WARNING: re.compile(r'\b(WARN|WARNING)\b', re.I),
    Severity.INFO: re.compile(r'\b(INFO|NOTICE)\b', re.I),
    Severity.DEBUG: re.compile(r'\b(DEBUG|TRACE|VERBOSE)\b', re.I),
}

CORRELATION_PATTERNS = {
    "request_id": re.compile(r'(?:request[_-]?id|req[_-]?id|x-request-id)[=:\s]+([a-zA-Z0-9\-_]+)', re.I),
    "session_id": re.compile(r'(?:session[_-]?id|sess[_-]?id)[=:\s]+([a-zA-Z0-9\-_]+)', re.I),
    "trace_id": re.compile(r'(?:trace[_-]?id|traceid)[=:\s]+([a-zA-Z0-9\-_]+)', re.I),
    "span_id": re.compile(r'(?:span[_-]?id|spanid)[=:\s]+([a-zA-Z0-9\-_]+)', re.I),
    "transaction_id": re.compile(r'(?:transaction[_-]?id|tx[_-]?id|txn[_-]?id)[=:\s]+([a-zA-Z0-9\-_]+)', re.I),
    "correlation_id": re.compile(r'(?:correlation[_-]?id|corr[_-]?id)[=:\s]+([a-zA-Z0-9\-_]+)', re.I),
}


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())[:12]


def detect_severity(line: str) -> Severity:
    """Detect severity level from log line."""
    for severity, pattern in SEVERITY_PATTERNS.items():
        if pattern.search(line):
            return severity
    return Severity.UNKNOWN


def extract_correlation_ids(line: str) -> dict[str, str]:
    """Extract correlation IDs from log line."""
    ids = {}
    for id_type, pattern in CORRELATION_PATTERNS.items():
        match = pattern.search(line)
        if match:
            ids[id_type] = match.group(1)
    return ids


def extract_component(line: str) -> str | None:
    """
    Extract component/logger name from log line.
    Common patterns: [component], <component>, component:
    """
    patterns = [
        re.compile(r'\[([a-zA-Z0-9_\-.]+)\]'),
        re.compile(r'<([a-zA-Z0-9_\-.]+)>'),
        re.compile(r'^[^\s]+\s+[^\s]+\s+([a-zA-Z0-9_\-.]+):'),
        re.compile(r'(?:logger|component|service)[=:\s]+([a-zA-Z0-9_\-.]+)', re.I),
    ]

    for pattern in patterns:
        match = pattern.search(line)
        if match:
            component = match.group(1)
            if len(component) > 2 and len(component) < 50:
                return component

    return None


class LogParser(ABC):
    """Abstract base class for log parsers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Parser name."""
        pass

    @property
    @abstractmethod
    def log_type(self) -> LogType:
        """Log type this parser handles."""
        pass

    @abstractmethod
    def can_parse(self, sample_lines: list[str]) -> float:
        """
        Check if this parser can handle the given lines.
        Returns confidence score 0.0 - 1.0.
        """
        pass

    @abstractmethod
    def parse_line(
        self,
        line: NormalizedLine,
        source_file: str,
    ) -> CanonicalEvent | None:
        """Parse a single line into a canonical event."""
        pass


class GenericParser(LogParser):
    """Generic parser that works with most log formats."""

    @property
    def name(self) -> str:
        return "generic"

    @property
    def log_type(self) -> LogType:
        return LogType.UNKNOWN

    def can_parse(self, sample_lines: list[str]) -> float:  # noqa: ARG002  # interface parity with concrete parsers
        return 0.1

    def parse_line(
        self,
        line: NormalizedLine,
        source_file: str,
    ) -> CanonicalEvent | None:
        if not line.content:
            return None

        return CanonicalEvent(
            id=generate_event_id(),
            timestamp=line.timestamp or datetime.now(timezone.utc),
            source=source_file,
            line_number=line.line_number,
            severity=detect_severity(line.content),
            component=extract_component(line.content),
            event_type=None,
            message=line.content,
            tags=[],
            correlation_ids=extract_correlation_ids(line.content),
            raw_line=line.original_line,
            log_type=self.log_type,
            metadata={},
        )


class BackendAppParser(LogParser):
    """Parser for backend application logs (Java, Python, Node.js)."""

    JAVA_PATTERN = re.compile(
        r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]\d+)\s+'
        r'(ERROR|WARN|INFO|DEBUG|TRACE)\s+'
        r'\[([^\]]+)\]\s+'
        r'([a-zA-Z0-9_.]+)\s*[-:]\s*(.+)',
        re.I
    )

    PYTHON_PATTERN = re.compile(
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.,]\d+)\s+'
        r'[-|]\s*(ERROR|WARNING|INFO|DEBUG)\s*[-|]\s*'
        r'([a-zA-Z0-9_.]+)\s*[-|:]\s*(.+)',
        re.I
    )

    EXCEPTION_PATTERN = re.compile(
        r'(Exception|Error|Throwable):\s*(.+)',
        re.I
    )

    STACK_TRACE_PATTERN = re.compile(
        r'^\s+at\s+([a-zA-Z0-9_.$]+)\(([^:]+):(\d+)\)',
    )

    @property
    def name(self) -> str:
        return "backend_app"

    @property
    def log_type(self) -> LogType:
        return LogType.BACKEND_APP

    def can_parse(self, sample_lines: list[str]) -> float:
        matches = 0.0
        for line in sample_lines[:20]:
            if self.JAVA_PATTERN.search(line) or self.PYTHON_PATTERN.search(line):
                matches += 1
            if self.EXCEPTION_PATTERN.search(line) or self.STACK_TRACE_PATTERN.search(line):
                matches += 0.5

        return min(1.0, matches / max(len(sample_lines[:20]), 1))

    def parse_line(
        self,
        line: NormalizedLine,
        source_file: str,
    ) -> CanonicalEvent | None:
        if not line.content:
            return None

        tags = []
        event_type = None

        if self.EXCEPTION_PATTERN.search(line.content):
            tags.append("exception")
            event_type = "exception"

        if self.STACK_TRACE_PATTERN.search(line.content):
            tags.append("stack_trace")
            event_type = "stack_trace"

        return CanonicalEvent(
            id=generate_event_id(),
            timestamp=line.timestamp or datetime.now(timezone.utc),
            source=source_file,
            line_number=line.line_number,
            severity=detect_severity(line.content),
            component=extract_component(line.content),
            event_type=event_type,
            message=line.content,
            tags=tags,
            correlation_ids=extract_correlation_ids(line.content),
            raw_line=line.original_line,
            log_type=self.log_type,
            metadata={},
        )


class ApiGatewayParser(LogParser):
    """Parser for API gateway/access logs (Nginx, Apache, Kong)."""

    NGINX_PATTERN = re.compile(
        r'(\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+'
        r'\[([^\]]+)\]\s+'
        r'"(\w+)\s+([^\s]+)\s+HTTP/[\d.]+"\s+'
        r'(\d+)\s+(\d+)\s+'
        r'"([^"]*)"\s+"([^"]*)"'
    )

    APACHE_PATTERN = re.compile(
        r'(\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+'
        r'\[([^\]]+)\]\s+'
        r'"(\w+)\s+([^\s]+)\s+HTTP/[\d.]+"\s+'
        r'(\d+)\s+(\d+)'
    )

    @property
    def name(self) -> str:
        return "api_gateway"

    @property
    def log_type(self) -> LogType:
        return LogType.API_GATEWAY

    def can_parse(self, sample_lines: list[str]) -> float:
        matches = 0
        for line in sample_lines[:20]:
            if self.NGINX_PATTERN.search(line) or self.APACHE_PATTERN.search(line):
                matches += 1

        return min(1.0, matches / max(len(sample_lines[:20]), 1))

    def parse_line(
        self,
        line: NormalizedLine,
        source_file: str,
    ) -> CanonicalEvent | None:
        if not line.content:
            return None

        metadata = {}
        tags = []
        severity = Severity.INFO

        nginx_match = self.NGINX_PATTERN.search(line.content)
        if nginx_match:
            status_code = int(nginx_match.group(5))
            metadata["client_ip"] = nginx_match.group(1)
            metadata["method"] = nginx_match.group(3)
            metadata["path"] = nginx_match.group(4)
            metadata["status_code"] = status_code
            metadata["bytes"] = int(nginx_match.group(6))

            if status_code >= 500:
                severity = Severity.ERROR
                tags.append("5xx")
            elif status_code >= 400:
                severity = Severity.WARNING
                tags.append("4xx")

        return CanonicalEvent(
            id=generate_event_id(),
            timestamp=line.timestamp or datetime.now(timezone.utc),
            source=source_file,
            line_number=line.line_number,
            severity=severity,
            component="gateway",
            event_type="access",
            message=line.content,
            tags=tags,
            correlation_ids=extract_correlation_ids(line.content),
            raw_line=line.original_line,
            log_type=self.log_type,
            metadata=metadata,
        )


class DatabaseParser(LogParser):
    """Parser for database logs (PostgreSQL, MySQL)."""

    POSTGRES_PATTERN = re.compile(
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.,]\d+\s+\w+)\s+'
        r'\[(\d+)\]\s+'
        r'(LOG|ERROR|WARNING|FATAL|PANIC|DEBUG|INFO|NOTICE):\s*(.+)',
        re.I
    )

    MYSQL_PATTERN = re.compile(
        r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]\d+)\s+'
        r'(\d+)\s+'
        r'\[(Note|Warning|Error)\]\s*(.+)',
        re.I
    )

    @property
    def name(self) -> str:
        return "database"

    @property
    def log_type(self) -> LogType:
        return LogType.DATABASE

    def can_parse(self, sample_lines: list[str]) -> float:
        matches = 0.0
        for line in sample_lines[:20]:
            if self.POSTGRES_PATTERN.search(line) or self.MYSQL_PATTERN.search(line):
                matches += 1
            if re.search(r'(deadlock|connection|query|transaction)', line, re.I):
                matches += 0.3

        return min(1.0, matches / max(len(sample_lines[:20]), 1))

    def parse_line(
        self,
        line: NormalizedLine,
        source_file: str,
    ) -> CanonicalEvent | None:
        if not line.content:
            return None

        tags = []
        metadata = {}

        if re.search(r'deadlock', line.content, re.I):
            tags.append("deadlock")
        if re.search(r'connection', line.content, re.I):
            tags.append("connection")
        if re.search(r'duration:\s*[\d.]+\s*ms', line.content, re.I):
            tags.append("slow_query")
            match = re.search(r'duration:\s*([\d.]+)\s*ms', line.content, re.I)
            if match:
                metadata["duration_ms"] = float(match.group(1))

        return CanonicalEvent(
            id=generate_event_id(),
            timestamp=line.timestamp or datetime.now(timezone.utc),
            source=source_file,
            line_number=line.line_number,
            severity=detect_severity(line.content),
            component="database",
            event_type=None,
            message=line.content,
            tags=tags,
            correlation_ids=extract_correlation_ids(line.content),
            raw_line=line.original_line,
            log_type=self.log_type,
            metadata=metadata,
        )


PARSERS: list[LogParser] = [
    BackendAppParser(),
    ApiGatewayParser(),
    DatabaseParser(),
    GenericParser(),
]


def select_parser(sample_lines: list[str]) -> LogParser:
    """
    Select the best parser for the given sample lines.
    Returns the parser with highest confidence.
    """
    best_parser = PARSERS[-1]
    best_score = 0.0

    for parser in PARSERS:
        score = parser.can_parse(sample_lines)
        if score > best_score:
            best_score = score
            best_parser = parser

    return best_parser


def parse_file(
    ingested_file: IngestedFile,
    normalization_result: NormalizationResult,
) -> ParsedFile:
    """
    Parse an ingested file into canonical events.

    Args:
        ingested_file: The ingested file
        normalization_result: Normalized lines from the file

    Returns:
        ParsedFile with all parsed events
    """
    sample_lines = [ln.content for ln in normalization_result.lines[:50]]
    parser = select_parser(sample_lines)

    events: list[CanonicalEvent] = []
    failed_lines = 0

    for line in normalization_result.lines:
        try:
            event = parser.parse_line(line, ingested_file.file_name)
            if event:
                events.append(event)
            else:
                failed_lines += 1
        except Exception:
            failed_lines += 1

    timestamps = [e.timestamp for e in events if e.timestamp]
    time_start = min(timestamps) if timestamps else None
    time_end = max(timestamps) if timestamps else None

    return ParsedFile(
        file_name=ingested_file.file_name,
        file_hash=ingested_file.file_hash,
        log_type=parser.log_type,
        events=events,
        total_lines=normalization_result.total_lines,
        parsed_lines=len(events),
        failed_lines=failed_lines,
        time_range_start=time_start,
        time_range_end=time_end,
    )
