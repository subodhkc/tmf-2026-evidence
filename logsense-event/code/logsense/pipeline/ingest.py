"""
Ingest Module
Safe file upload handling with validation, hashing, and zip extraction.
"""

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from logsense.config.constants import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    ErrorCode,
)


@dataclass
class IngestedFile:
    """Represents a single ingested file."""

    file_name: str
    content: bytes
    file_hash: str
    size_bytes: int
    extension: str


@dataclass
class IngestionManifest:
    """Manifest of all ingested files."""

    analysis_id: str
    input_hash: str
    files: list[IngestedFile]
    ingested_at: datetime
    total_size_bytes: int

    @property
    def file_count(self) -> int:
        return len(self.files)


class IngestionError(Exception):
    """Base exception for ingestion errors."""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


class FileTooLargeError(IngestionError):
    """File exceeds size limit."""

    def __init__(self, file_name: str, size_bytes: int, max_bytes: int):
        super().__init__(
            f"File '{file_name}' ({size_bytes} bytes) exceeds maximum size ({max_bytes} bytes)",
            ErrorCode.FILE_TOO_LARGE
        )


class InvalidFileTypeError(IngestionError):
    """File type not allowed."""

    def __init__(self, file_name: str, extension: str):
        super().__init__(
            f"File '{file_name}' has invalid extension '{extension}'. Allowed: {ALLOWED_EXTENSIONS}",
            ErrorCode.INVALID_FILE_TYPE
        )


class ZipSlipError(IngestionError):
    """Zip slip attack detected."""

    def __init__(self, file_name: str):
        super().__init__(
            f"Zip slip attack detected in file '{file_name}'",
            ErrorCode.INVALID_FILE_TYPE
        )


def compute_hash(content: bytes) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def compute_analysis_id(files: list[IngestedFile]) -> str:
    """
    Compute deterministic analysis ID from file hashes.
    Same files always produce same analysis_id.
    """
    combined = "".join(sorted(f.file_hash for f in files))
    return compute_hash(combined.encode())[:16]


def sanitize_filename(file_name: str) -> str:
    """
    Sanitize filename to prevent path traversal.
    Removes directory components and dangerous characters.
    """
    # Normalize Windows separators before basename extraction so a Windows path
    # is treated as a path even when LogSense runs on POSIX.
    name = Path(str(file_name).replace("\\", "/")).name
    name = name.replace("..", "").replace("/", "").replace("\\", "")
    if not name:
        name = "unnamed_file"
    return name


def validate_extension(file_name: str) -> str:
    """
    Validate file extension is allowed.
    Returns the extension if valid, raises InvalidFileTypeError otherwise.
    """
    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(file_name, ext)
    return ext


def validate_size(file_name: str, size_bytes: int, max_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
    """Validate file size is within limits."""
    if size_bytes > max_bytes:
        raise FileTooLargeError(file_name, size_bytes, max_bytes)


def is_safe_zip_path(zip_path: str, extract_dir: str) -> bool:
    """
    Check if zip path is safe (no zip slip attack).
    Returns True if path is safe, False otherwise.
    """
    abs_extract = os.path.abspath(extract_dir)
    abs_target = os.path.abspath(os.path.join(extract_dir, zip_path))
    return abs_target.startswith(abs_extract)


def extract_zip(
    zip_content: bytes,
    max_total_size: int = MAX_FILE_SIZE_BYTES * 10
) -> list[tuple[str, bytes]]:
    """
    Safely extract files from a ZIP archive.

    Args:
        zip_content: Raw ZIP file bytes
        max_total_size: Maximum total extracted size

    Returns:
        List of (filename, content) tuples

    Raises:
        ZipSlipError: If zip slip attack detected
        FileTooLargeError: If extracted content too large
    """
    extracted = []
    total_size = 0

    with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue

            file_name = sanitize_filename(info.filename)

            if not is_safe_zip_path(info.filename, "/tmp"):  # nosec B108  # synthetic containment anchor, not a real temp path
                raise ZipSlipError(info.filename)

            ext = Path(file_name).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS or ext == ".zip":
                continue

            content = zf.read(info.filename)
            total_size += len(content)

            if total_size > max_total_size:
                raise FileTooLargeError(
                    "ZIP contents", total_size, max_total_size
                )

            extracted.append((file_name, content))

    return extracted


def ingest_file(
    file_name: str,
    content: bytes,
    max_size: int = MAX_FILE_SIZE_BYTES
) -> IngestedFile:
    """
    Ingest a single file with validation.

    Args:
        file_name: Original file name
        content: File content bytes
        max_size: Maximum allowed size

    Returns:
        IngestedFile object

    Raises:
        InvalidFileTypeError: If file type not allowed
        FileTooLargeError: If file too large
    """
    safe_name = sanitize_filename(file_name)
    ext = validate_extension(safe_name)
    validate_size(safe_name, len(content), max_size)

    return IngestedFile(
        file_name=safe_name,
        content=content,
        file_hash=compute_hash(content),
        size_bytes=len(content),
        extension=ext,
    )


def ingest_files(
    files: list[tuple[str, bytes]],
    max_file_size: int = MAX_FILE_SIZE_BYTES,
    max_total_size: int = MAX_FILE_SIZE_BYTES * 10,
) -> IngestionManifest:
    """
    Ingest multiple files, handling ZIP extraction.

    Args:
        files: List of (filename, content) tuples
        max_file_size: Maximum size per file
        max_total_size: Maximum total size

    Returns:
        IngestionManifest with all ingested files

    Raises:
        IngestionError: On validation failure
    """
    ingested: list[IngestedFile] = []
    total_size = 0

    for file_name, content in files:
        ext = Path(file_name).suffix.lower()

        if ext == ".zip":
            extracted = extract_zip(content, max_total_size)
            for extracted_name, extracted_content in extracted:
                ingested_file = ingest_file(
                    extracted_name, extracted_content, max_file_size
                )
                ingested.append(ingested_file)
                total_size += ingested_file.size_bytes
        else:
            ingested_file = ingest_file(file_name, content, max_file_size)
            ingested.append(ingested_file)
            total_size += ingested_file.size_bytes

        if total_size > max_total_size:
            raise FileTooLargeError("Total files", total_size, max_total_size)

    analysis_id = compute_analysis_id(ingested)
    input_hash = compute_hash(
        b"".join(f.content for f in sorted(ingested, key=lambda x: x.file_name))
    )

    return IngestionManifest(
        analysis_id=analysis_id,
        input_hash=input_hash,
        files=ingested,
        ingested_at=datetime.now(timezone.utc),
        total_size_bytes=total_size,
    )


def ingest_from_bytes(
    file_name: str,
    content: bytes,
) -> IngestionManifest:
    """
    Convenience function to ingest a single file from bytes.
    """
    return ingest_files([(file_name, content)])


def ingest_from_path(file_path: Path) -> IngestionManifest:
    """
    Convenience function to ingest a file from disk.
    """
    with open(file_path, "rb") as f:
        content = f.read()
    return ingest_files([(file_path.name, content)])
