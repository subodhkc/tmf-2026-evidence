"""
Normalize Module
Encoding detection, line normalization, and timestamp parsing.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import chardet
from dateutil import parser as date_parser


class TimestampFormat(Enum):
    """Common timestamp formats."""
    ISO8601 = "iso8601"
    WINDOWS = "windows"
    SYSLOG = "syslog"
    APACHE = "apache"
    NGINX = "nginx"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


@dataclass
class NormalizedLine:
    """A single normalized log line."""

    line_number: int
    content: str
    timestamp: datetime | None
    timestamp_format: TimestampFormat
    original_line: str


@dataclass
class NormalizationResult:
    """Result of normalizing a file's content."""

    lines: list[NormalizedLine]
    encoding: str
    total_lines: int
    lines_with_timestamp: int
    lines_without_timestamp: int
    detected_format: TimestampFormat
    has_gaps: bool
    gap_locations: list[tuple[int, int]]


TIMESTAMP_PATTERNS = [
    (
        TimestampFormat.ISO8601,
        re.compile(
            r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)'
        )
    ),
    (
        TimestampFormat.WINDOWS,
        re.compile(
            r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}(?:\s*[AP]M)?)'
        )
    ),
    (
        TimestampFormat.SYSLOG,
        re.compile(
            r'([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})'
        )
    ),
    (
        TimestampFormat.APACHE,
        re.compile(
            r'\[(\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2}\s*[+-]\d{4})\]'
        )
    ),
    (
        TimestampFormat.NGINX,
        re.compile(
            r'\[(\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2}\s*[+-]\d{4})\]'
        )
    ),
    (
        TimestampFormat.CUSTOM,
        re.compile(
            r'(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})'
        )
    ),
]


def detect_encoding(content: bytes) -> str:
    """
    Detect the encoding of byte content.
    Falls back to utf-8 if detection fails.
    """
    result = chardet.detect(content)
    encoding = result.get("encoding")

    if encoding is None:
        return "utf-8"

    encoding = encoding.lower()
    if encoding in ("ascii", "utf-8", "utf8"):
        return "utf-8"

    return encoding


def decode_content(content: bytes, encoding: str | None = None) -> tuple[str, str]:
    """
    Decode byte content to string.

    Returns:
        Tuple of (decoded_string, detected_encoding)
    """
    if encoding is None:
        encoding = detect_encoding(content)

    try:
        decoded = content.decode(encoding, errors="replace")
    except (UnicodeDecodeError, LookupError):
        decoded = content.decode("utf-8", errors="replace")
        encoding = "utf-8"

    return decoded, encoding


def normalize_line_endings(text: str) -> str:
    """Normalize line endings to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def extract_timestamp(line: str) -> tuple[datetime | None, TimestampFormat]:
    """
    Extract timestamp from a log line.

    Returns:
        Tuple of (datetime or None, format detected)
    """
    for fmt, pattern in TIMESTAMP_PATTERNS:
        match = pattern.search(line)
        if match:
            timestamp_str = match.group(1)
            try:
                dt = date_parser.parse(timestamp_str, fuzzy=True)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt, fmt
            except (ValueError, OverflowError):
                continue

    return None, TimestampFormat.UNKNOWN


def detect_gaps(
    lines: list[NormalizedLine],
    max_gap_seconds: int = 3600
) -> list[tuple[int, int]]:
    """
    Detect time gaps in log lines.

    Args:
        lines: List of normalized lines with timestamps
        max_gap_seconds: Maximum expected gap between consecutive lines

    Returns:
        List of (start_line, end_line) tuples indicating gaps
    """
    gaps = []
    timestamped = [(ln.line_number, ln.timestamp) for ln in lines if ln.timestamp]

    for i in range(1, len(timestamped)):
        prev_line, prev_ts = timestamped[i - 1]
        curr_line, curr_ts = timestamped[i]

        if prev_ts and curr_ts:
            diff = (curr_ts - prev_ts).total_seconds()
            if diff > max_gap_seconds:
                gaps.append((prev_line, curr_line))

    return gaps


def normalize_lines(content: str) -> Iterator[tuple[int, str]]:
    """
    Yield normalized lines with line numbers.

    Args:
        content: Decoded file content

    Yields:
        Tuples of (line_number, line_content)
    """
    content = normalize_line_endings(content)
    for i, line in enumerate(content.split("\n"), start=1):
        stripped = line.strip()
        if stripped:
            yield i, stripped


def normalize_file(
    content: bytes,
    encoding: str | None = None
) -> NormalizationResult:
    """
    Normalize a log file's content.

    Args:
        content: Raw file bytes
        encoding: Optional encoding override

    Returns:
        NormalizationResult with normalized lines
    """
    decoded, detected_encoding = decode_content(content, encoding)

    lines: list[NormalizedLine] = []
    format_counts: dict = {}

    for line_num, line_content in normalize_lines(decoded):
        timestamp, fmt = extract_timestamp(line_content)

        normalized = NormalizedLine(
            line_number=line_num,
            content=line_content,
            timestamp=timestamp,
            timestamp_format=fmt,
            original_line=line_content,
        )
        lines.append(normalized)

        if fmt != TimestampFormat.UNKNOWN:
            format_counts[fmt] = format_counts.get(fmt, 0) + 1

    lines_with_ts = sum(1 for ln in lines if ln.timestamp)
    lines_without_ts = len(lines) - lines_with_ts

    detected_format = TimestampFormat.UNKNOWN
    if format_counts:
        detected_format = max(format_counts, key=format_counts.__getitem__)

    gaps = detect_gaps(lines)

    return NormalizationResult(
        lines=lines,
        encoding=detected_encoding,
        total_lines=len(lines),
        lines_with_timestamp=lines_with_ts,
        lines_without_timestamp=lines_without_ts,
        detected_format=detected_format,
        has_gaps=len(gaps) > 0,
        gap_locations=gaps,
    )


def normalize_to_utc(dt: datetime) -> datetime:
    """Ensure datetime is in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
