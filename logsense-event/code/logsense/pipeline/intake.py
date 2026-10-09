from __future__ import annotations

import hashlib
import mimetypes
import stat
import tarfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import IO

from logsense.adapters.registry import AdapterRegistry, AdapterSelection, load_default_registry
from logsense.config.constants import MAX_FILE_SIZE_BYTES

DEFAULT_MAX_FILE_COUNT = 1000
DEFAULT_MAX_TOTAL_BYTES = MAX_FILE_SIZE_BYTES * 40
DEFAULT_MAX_ARCHIVE_FILES = 1000
DEFAULT_MAX_EXPANDED_BYTES = MAX_FILE_SIZE_BYTES * 40
DEFAULT_MAX_COMPRESSION_RATIO = 100.0
STREAM_CHUNK_BYTES = 1024 * 1024
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")


class EvidenceIntakeError(Exception):
    """Base deterministic local evidence intake error."""


class EvidencePathError(EvidenceIntakeError):
    pass


class EvidenceSymlinkError(EvidenceIntakeError):
    pass


class EvidenceLimitError(EvidenceIntakeError):
    pass


class EvidenceChangedError(EvidenceIntakeError):
    pass


class EvidencePathCollisionError(EvidenceIntakeError):
    pass


class EvidenceArchiveError(EvidenceIntakeError):
    pass


@dataclass(frozen=True)
class ArchiveContainer:
    logical_path: str
    source_path: Path
    size_bytes: int
    sha256: str
    media_type: str

    @property
    def artifact_id(self) -> str:
        return f"artifact:{self.sha256[:24]}"

    def forensic_artifact(self, ingested_at: datetime) -> dict:
        return {
            "artifactId": self.artifact_id,
            "originalName": self.logical_path,
            "mediaType": self.media_type,
            "sizeBytes": self.size_bytes,
            "sha256": self.sha256,
            "ingestedAt": ingested_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pathOrVaultRef": self.logical_path,
            "parseStatus": "PARTIAL",
            "limitations": ["ARCHIVE_CONTAINER_EXPANDED", "MEMBER_ARTIFACTS_PRESERVED_SEPARATELY"],
        }


@dataclass(frozen=True)
class EvidenceManifestEntry:
    logical_path: str
    source_path: Path
    size_bytes: int
    sha256: str
    media_type: str
    adapter_id: str
    adapter_version: str
    format_family: str
    limitations: tuple[str, ...]
    archive_member: str | None = None
    archive_kind: str | None = None
    archive_parent_sha256: str | None = None

    @property
    def artifact_id(self) -> str:
        return f"artifact:{self.sha256[:24]}"

    @property
    def archive_parent_artifact_id(self) -> str | None:
        if self.archive_parent_sha256 is None:
            return None
        return f"artifact:{self.archive_parent_sha256[:24]}"

    @property
    def source_id(self) -> str:
        seed = f"{self.logical_path}\0{self.sha256}".encode()
        return f"source:{hashlib.sha256(seed).hexdigest()[:24]}"

    def forensic_artifact(self, ingested_at: datetime) -> dict:
        value = {
            "artifactId": self.artifact_id,
            "originalName": self.logical_path,
            "mediaType": self.media_type,
            "sizeBytes": self.size_bytes,
            "sha256": self.sha256,
            "ingestedAt": ingested_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pathOrVaultRef": self.logical_path,
            "parseStatus": "PENDING",
            "limitations": list(self.limitations),
        }
        if self.archive_parent_artifact_id is not None:
            value["compressionParentRef"] = self.archive_parent_artifact_id
        return value

    def source_descriptor(self) -> dict:
        lineage_parent = self.archive_parent_artifact_id
        return {
            "sourceId": self.source_id,
            "sourceSystem": "LOCAL_EVIDENCE_INTAKE",
            "sourceKind": self.format_family,
            "authorityRoleCandidate": "UNKNOWN_SOURCE_AUTHORITY",
            "authorityBasis": "LOCAL_ARTIFACT_ONLY",
            "authorityLimitations": ["SOURCE_AUTHORITY_NOT_ESTABLISHED"],
            "lineageFamilyId": lineage_parent or self.artifact_id,
            "lineageParentRef": lineage_parent,
            "lineageRelation": "DERIVED" if lineage_parent else "ORIGINAL",
            "environment": None,
            "producer": None,
            "adapterId": self.adapter_id,
            "adapterVersion": self.adapter_version,
            "declaredCanEstablish": [],
            "declaredCannotEstablish": ["FORENSIC_SEMANTICS", "CANONICAL_RELATION", "CAUSE_STATE"],
            "integrityState": "PARTIAL",
            "completenessState": "UNKNOWN",
            "currentness": "UNKNOWN",
            "limitations": sorted(set(self.limitations + (
                "LOCAL_FILE_HASH_VERIFIED_ONLY",
                "SOURCE_AUTHORITY_UNQUALIFIED",
            ))),
        }


@dataclass(frozen=True)
class EvidenceManifest:
    manifest_id: str
    dataset_digest: str
    entries: tuple[EvidenceManifestEntry, ...]
    archive_containers: tuple[ArchiveContainer, ...]
    total_size_bytes: int

    @property
    def file_count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class CommittedEvidence:
    manifest: EvidenceManifest
    artifacts: tuple[dict, ...]
    archive_artifacts: tuple[dict, ...]
    source_descriptors: tuple[dict, ...]
    contents: tuple[bytes, ...]


def _stream_hash(path: Path, chunk_size: int = STREAM_CHUNK_BYTES) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), total


def _hash_stream(stream: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(STREAM_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        digest.update(chunk)
    return digest.hexdigest(), total


def _logical_path(path: Path, root: Path | None) -> str:
    if root is None:
        return path.name
    return f"{root.name}/{path.relative_to(root).as_posix()}"


def _archive_kind(path: Path) -> str | None:
    lower = path.name.lower()
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return "tar.gz"
    if lower.endswith(".tar"):
        return "tar"
    return None


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise EvidenceArchiveError(f"absolute archive member path rejected: {name}")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise EvidenceArchiveError(f"unsafe archive member path rejected: {name}")
    return PurePosixPath(*parts).as_posix()


def _is_nested_archive(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(ARCHIVE_SUFFIXES)


def _enumerate_paths(paths: Iterable[Path]) -> list[tuple[Path, Path | None]]:
    found: list[tuple[Path, Path | None]] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise EvidencePathError(f"evidence path does not exist: {path}")
        if path.is_symlink():
            raise EvidenceSymlinkError(f"symlink evidence path rejected: {path}")
        if path.is_file():
            found.append((path, None))
            continue
        if not path.is_dir():
            raise EvidencePathError(f"unsupported evidence path: {path}")
        for child in sorted(path.rglob("*"), key=lambda p: p.as_posix()):
            if child.is_symlink():
                raise EvidenceSymlinkError(f"symlink inside evidence directory rejected: {child}")
            if child.is_file():
                found.append((child, path))
    return found


def _member_entry(
    *,
    archive: ArchiveContainer,
    member_name: str,
    member_hash: str,
    member_size: int,
    archive_kind: str,
    registry: AdapterRegistry,
) -> EvidenceManifestEntry:
    media_type = mimetypes.guess_type(member_name)[0] or "application/octet-stream"
    selection: AdapterSelection = registry.select(member_name, media_type=media_type)
    return EvidenceManifestEntry(
        logical_path=f"{archive.logical_path}/{member_name}",
        source_path=archive.source_path,
        size_bytes=member_size,
        sha256=member_hash,
        media_type=media_type,
        adapter_id=selection.adapter.adapter_id,
        adapter_version=selection.adapter.adapter_version,
        format_family=selection.adapter.formats[0] if selection.adapter.formats else "opaque",
        limitations=tuple(sorted(set(selection.adapter.limitations + selection.limitations + ("ARCHIVE_MEMBER",)))),
        archive_member=member_name,
        archive_kind=archive_kind,
        archive_parent_sha256=archive.sha256,
    )


def _scan_zip(
    archive: ArchiveContainer,
    *,
    registry: AdapterRegistry,
    max_archive_files: int,
    max_expanded_bytes: int,
    max_compression_ratio: float,
) -> list[EvidenceManifestEntry]:
    entries: list[EvidenceManifestEntry] = []
    total_expanded = 0
    names: set[str] = set()
    with zipfile.ZipFile(archive.source_path, "r") as zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        if len(infos) > max_archive_files:
            raise EvidenceLimitError(f"archive file count {len(infos)} exceeds limit {max_archive_files}")
        for info in infos:
            name = _safe_member_name(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(mode):
                raise EvidenceArchiveError(f"archive symlink rejected: {info.filename}")
            if info.flag_bits & 0x1:
                raise EvidenceArchiveError(f"encrypted archive member rejected: {info.filename}")
            if _is_nested_archive(name):
                raise EvidenceArchiveError(f"nested archive rejected: {name}")
            if name in names:
                raise EvidencePathCollisionError(f"duplicate archive member path: {name}")
            names.add(name)
            total_expanded += info.file_size
            if total_expanded > max_expanded_bytes:
                raise EvidenceLimitError(f"archive expanded bytes {total_expanded} exceeds limit {max_expanded_bytes}")
            if info.file_size and info.compress_size == 0:
                raise EvidenceLimitError(f"archive member has unbounded compression ratio: {name}")
            ratio = (info.file_size / info.compress_size) if info.compress_size else 0.0
            if ratio > max_compression_ratio:
                raise EvidenceLimitError(f"archive member compression ratio {ratio:.2f} exceeds limit {max_compression_ratio}")
            with zf.open(info, "r") as stream:
                digest, actual_size = _hash_stream(stream)
            if actual_size != info.file_size:
                raise EvidenceArchiveError(f"archive member size mismatch: {name}")
            entries.append(_member_entry(
                archive=archive, member_name=name, member_hash=digest, member_size=actual_size,
                archive_kind="zip", registry=registry,
            ))
    if archive.size_bytes and total_expanded / archive.size_bytes > max_compression_ratio:
        raise EvidenceLimitError("archive overall compression ratio exceeds limit")
    return entries


def _scan_tar(
    archive: ArchiveContainer,
    *,
    registry: AdapterRegistry,
    max_archive_files: int,
    max_expanded_bytes: int,
    max_compression_ratio: float,
) -> list[EvidenceManifestEntry]:
    entries: list[EvidenceManifestEntry] = []
    total_expanded = 0
    names: set[str] = set()
    with tarfile.open(archive.source_path, "r:*") as tf:
        members = [m for m in tf.getmembers() if not m.isdir()]
        if len(members) > max_archive_files:
            raise EvidenceLimitError(f"archive file count {len(members)} exceeds limit {max_archive_files}")
        for member in members:
            name = _safe_member_name(member.name)
            if member.issym() or member.islnk():
                raise EvidenceArchiveError(f"archive link rejected: {member.name}")
            if not member.isfile():
                raise EvidenceArchiveError(f"archive special member rejected: {member.name}")
            if _is_nested_archive(name):
                raise EvidenceArchiveError(f"nested archive rejected: {name}")
            if name in names:
                raise EvidencePathCollisionError(f"duplicate archive member path: {name}")
            names.add(name)
            total_expanded += member.size
            if total_expanded > max_expanded_bytes:
                raise EvidenceLimitError(f"archive expanded bytes {total_expanded} exceeds limit {max_expanded_bytes}")
            stream = tf.extractfile(member)
            if stream is None:
                raise EvidenceArchiveError(f"archive member could not be read: {name}")
            with stream:
                digest, actual_size = _hash_stream(stream)
            if actual_size != member.size:
                raise EvidenceArchiveError(f"archive member size mismatch: {name}")
            entries.append(_member_entry(
                archive=archive, member_name=name, member_hash=digest, member_size=actual_size,
                archive_kind="tar", registry=registry,
            ))
    if archive.size_bytes and total_expanded / archive.size_bytes > max_compression_ratio:
        raise EvidenceLimitError("archive overall compression ratio exceeds limit")
    return entries


def _scan_archive(
    path: Path,
    logical_path: str,
    *,
    registry: AdapterRegistry,
    max_archive_files: int,
    max_expanded_bytes: int,
    max_compression_ratio: float,
) -> tuple[ArchiveContainer, list[EvidenceManifestEntry]]:
    digest, size = _stream_hash(path)
    kind = _archive_kind(path)
    if kind is None:
        raise EvidenceArchiveError(f"unsupported archive format: {path.name}")
    archive = ArchiveContainer(
        logical_path=logical_path,
        source_path=path.absolute(),
        size_bytes=size,
        sha256=digest,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )
    if kind == "zip":
        entries = _scan_zip(
            archive, registry=registry, max_archive_files=max_archive_files,
            max_expanded_bytes=max_expanded_bytes, max_compression_ratio=max_compression_ratio,
        )
    else:
        entries = _scan_tar(
            archive, registry=registry, max_archive_files=max_archive_files,
            max_expanded_bytes=max_expanded_bytes, max_compression_ratio=max_compression_ratio,
        )
    return archive, entries


def preview_evidence(
    paths: Iterable[Path],
    *,
    max_file_size: int = MAX_FILE_SIZE_BYTES,
    max_file_count: int = DEFAULT_MAX_FILE_COUNT,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_archive_files: int = DEFAULT_MAX_ARCHIVE_FILES,
    max_expanded_bytes: int = DEFAULT_MAX_EXPANDED_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> EvidenceManifest:
    registry = load_default_registry()
    discovered = _enumerate_paths(paths)
    entries: list[EvidenceManifestEntry] = []
    archives: list[ArchiveContainer] = []
    logical_seen: set[str] = set()
    total = 0

    for path, root in discovered:
        logical = _logical_path(path, root)
        kind = _archive_kind(path)
        if kind is not None:
            archive, member_entries = _scan_archive(
                path, logical, registry=registry, max_archive_files=max_archive_files,
                max_expanded_bytes=max_expanded_bytes, max_compression_ratio=max_compression_ratio,
            )
            archives.append(archive)
            total += sum(e.size_bytes for e in member_entries)
            for entry in member_entries:
                if entry.logical_path in logical_seen:
                    raise EvidencePathCollisionError(f"duplicate logical evidence path: {entry.logical_path}")
                logical_seen.add(entry.logical_path)
                entries.append(entry)
        else:
            digest, size = _stream_hash(path)
            if size > max_file_size:
                raise EvidenceLimitError(f"file {logical} size {size} exceeds limit {max_file_size}")
            total += size
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            selection: AdapterSelection = registry.select(path.name, media_type=media_type)
            entry = EvidenceManifestEntry(
                logical_path=logical, source_path=path.absolute(), size_bytes=size, sha256=digest,
                media_type=media_type, adapter_id=selection.adapter.adapter_id,
                adapter_version=selection.adapter.adapter_version,
                format_family=selection.adapter.formats[0] if selection.adapter.formats else "opaque",
                limitations=tuple(sorted(set(selection.adapter.limitations + selection.limitations))),
            )
            if entry.logical_path in logical_seen:
                raise EvidencePathCollisionError(f"duplicate logical evidence path: {entry.logical_path}")
            logical_seen.add(entry.logical_path)
            entries.append(entry)

        if len(entries) > max_file_count:
            raise EvidenceLimitError(f"file count {len(entries)} exceeds limit {max_file_count}")
        if total > max_total_bytes:
            raise EvidenceLimitError(f"total evidence bytes {total} exceeds limit {max_total_bytes}")

    entries.sort(key=lambda x: x.logical_path)
    archives.sort(key=lambda x: x.logical_path)
    dataset_seed = "".join(f"{e.logical_path}\0{e.sha256}\0{e.size_bytes}\n" for e in entries).encode("utf-8")
    dataset_digest = hashlib.sha256(dataset_seed).hexdigest()
    return EvidenceManifest(
        manifest_id=f"manifest:{dataset_digest[:24]}", dataset_digest=dataset_digest,
        entries=tuple(entries), archive_containers=tuple(archives), total_size_bytes=total,
    )


def _read_archive_member(entry: EvidenceManifestEntry) -> bytes:
    if entry.archive_member is None or entry.archive_kind is None:
        return entry.source_path.read_bytes()
    if entry.archive_kind == "zip":
        with zipfile.ZipFile(entry.source_path, "r") as zf:
            return zf.read(entry.archive_member)
    with tarfile.open(entry.source_path, "r:*") as tf:
        member = tf.getmember(entry.archive_member)
        stream = tf.extractfile(member)
        if stream is None:
            raise EvidenceArchiveError(f"archive member could not be read: {entry.archive_member}")
        with stream:
            return stream.read()


def commit_evidence(manifest: EvidenceManifest) -> CommittedEvidence:
    committed_at = datetime.now(timezone.utc)
    parent_by_sha = {a.sha256: a for a in manifest.archive_containers}
    checked_parents: set[str] = set()
    archive_artifacts = tuple(a.forensic_artifact(committed_at) for a in manifest.archive_containers)
    artifacts: list[dict] = []
    source_descriptors: list[dict] = []
    contents: list[bytes] = []
    for entry in manifest.entries:
        if entry.archive_parent_sha256 is not None and entry.archive_parent_sha256 not in checked_parents:
            parent = parent_by_sha[entry.archive_parent_sha256]
            parent_digest, parent_size = _stream_hash(parent.source_path)
            if parent_digest != parent.sha256 or parent_size != parent.size_bytes:
                raise EvidenceChangedError(f"archive changed after preview: {parent.logical_path}")
            checked_parents.add(entry.archive_parent_sha256)
        content = _read_archive_member(entry)
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry.sha256 or len(content) != entry.size_bytes:
            raise EvidenceChangedError(f"evidence changed after preview: {entry.logical_path}")
        contents.append(content)
        artifacts.append(entry.forensic_artifact(committed_at))
        source_descriptors.append(entry.source_descriptor())
    return CommittedEvidence(
        manifest=manifest, artifacts=tuple(artifacts), archive_artifacts=archive_artifacts,
        source_descriptors=tuple(source_descriptors), contents=tuple(contents),
    )
