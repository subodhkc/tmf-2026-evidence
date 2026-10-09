from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logsense.pipeline.intake import CommittedEvidence

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CASE_DIRS = ("artifacts", "manifests", "profiles", "runs", "projections", "reports", "exports")
_SCHEMA_VERSION = 1


class CaseWorkspaceError(Exception):
    """Base local case-workspace error."""


class InvalidCaseIdError(CaseWorkspaceError):
    pass


class CaseExistsError(CaseWorkspaceError):
    pass


class CaseNotFoundError(CaseWorkspaceError):
    pass


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    title: str
    created_at: str
    updated_at: str
    schema_version: int = _SCHEMA_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_case_id(case_id: str) -> str:
    value = str(case_id).strip()
    if not _CASE_ID_RE.fullmatch(value):
        raise InvalidCaseIdError(
            "case ID must start with an alphanumeric character and contain only letters, numbers, '.', '_' or '-'"
        )
    return value


def _cases_root(workspace_root: Path) -> Path:
    return Path(workspace_root).expanduser().resolve() / "cases"


def case_path(workspace_root: Path, case_id: str) -> Path:
    return _cases_root(workspace_root) / _validate_case_id(case_id)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _initialize_db(db_path: Path) -> None:
    with _connect(db_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS manifests (
                manifest_id TEXT PRIMARY KEY,
                dataset_digest TEXT NOT NULL,
                file_count INTEGER NOT NULL,
                total_size_bytes INTEGER NOT NULL,
                committed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                manifest_id TEXT NOT NULL,
                logical_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                media_type TEXT,
                adapter_id TEXT,
                adapter_version TEXT,
                format_family TEXT,
                stored_path TEXT NOT NULL,
                FOREIGN KEY(manifest_id) REFERENCES manifests(manifest_id)
            );
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT NOT NULL,
                manifest_id TEXT NOT NULL,
                source_kind TEXT,
                adapter_id TEXT,
                adapter_version TEXT,
                descriptor_json TEXT NOT NULL,
                PRIMARY KEY(source_id, manifest_id),
                FOREIGN KEY(manifest_id) REFERENCES manifests(manifest_id)
            );
            """)
        db.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
            (str(_SCHEMA_VERSION),),
        )


def create_case(
    workspace_root: Path,
    *,
    case_id: str,
    title: str | None = None,
    created_at: str | None = None,
) -> CaseRecord:
    case_id = _validate_case_id(case_id)
    root = case_path(workspace_root, case_id)
    if root.exists():
        raise CaseExistsError(f"case already exists: {case_id}")
    root.mkdir(parents=True)
    for directory in _CASE_DIRS:
        (root / directory).mkdir()
    timestamp = created_at or _utc_now()
    record = CaseRecord(
        case_id=case_id,
        title=(title or case_id).strip() or case_id,
        created_at=timestamp,
        updated_at=timestamp,
    )
    _atomic_json(root / "case.json", asdict(record))
    _initialize_db(root / "case.db")
    return record


def load_case(workspace_root: Path, case_id: str) -> CaseRecord:
    root = case_path(workspace_root, case_id)
    metadata_path = root / "case.json"
    if not metadata_path.is_file() or not (root / "case.db").is_file():
        raise CaseNotFoundError(f"case not found: {case_id}")
    value = json.loads(metadata_path.read_text(encoding="utf-8"))
    return CaseRecord(
        case_id=str(value["case_id"]),
        title=str(value["title"]),
        created_at=str(value["created_at"]),
        updated_at=str(value["updated_at"]),
        schema_version=int(value.get("schema_version", _SCHEMA_VERSION)),
    )


def list_cases(workspace_root: Path) -> tuple[CaseRecord, ...]:
    root = _cases_root(workspace_root)
    if not root.exists():
        return ()
    rows: list[CaseRecord] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        try:
            rows.append(load_case(workspace_root, child.name))
        except (CaseWorkspaceError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return tuple(sorted(rows, key=lambda row: (row.updated_at, row.case_id), reverse=True))


def _manifest_payload(committed: CommittedEvidence, committed_at: str) -> dict[str, Any]:
    manifest = committed.manifest
    entries = []
    for entry in manifest.entries:
        entries.append(
            {
                "artifactId": entry.artifact_id,
                "sourceId": entry.source_id,
                "logicalPath": entry.logical_path,
                "sizeBytes": entry.size_bytes,
                "sha256": entry.sha256,
                "mediaType": entry.media_type,
                "adapterId": entry.adapter_id,
                "adapterVersion": entry.adapter_version,
                "formatFamily": entry.format_family,
                "limitations": list(entry.limitations),
                "archiveParentArtifactId": entry.archive_parent_artifact_id,
            }
        )
    return {
        "manifestId": manifest.manifest_id,
        "datasetDigest": manifest.dataset_digest,
        "fileCount": manifest.file_count,
        "totalSizeBytes": manifest.total_size_bytes,
        "committedAt": committed_at,
        "entries": entries,
    }


def commit_evidence_to_case(
    workspace_root: Path,
    *,
    case_id: str,
    committed: CommittedEvidence,
    committed_at: str | None = None,
) -> dict[str, Any]:
    """Persist already-committed immutable evidence without changing its semantics."""
    record = load_case(workspace_root, case_id)
    root = case_path(workspace_root, record.case_id)
    timestamp = committed_at or _utc_now()
    manifest = committed.manifest
    payload = _manifest_payload(committed, timestamp)
    manifest_path = root / "manifests" / f"{manifest.manifest_id.replace(':', '_')}.json"

    if len(committed.contents) != len(manifest.entries):
        raise CaseWorkspaceError("committed evidence content count does not match manifest")
    if len(committed.source_descriptors) != len(manifest.entries):
        raise CaseWorkspaceError("source descriptor count does not match manifest")

    stored_paths: list[str] = []
    for entry, content in zip(manifest.entries, committed.contents, strict=False):
        stored = root / "artifacts" / f"{entry.sha256}.bin"
        if stored.exists():
            if stored.read_bytes() != content:
                raise CaseWorkspaceError(f"stored artifact digest collision: {entry.artifact_id}")
        else:
            stored.write_bytes(content)
        stored_paths.append(stored.relative_to(root).as_posix())

    with _connect(root / "case.db") as db:
        existing = db.execute(
            "SELECT dataset_digest FROM manifests WHERE manifest_id = ?",
            (manifest.manifest_id,),
        ).fetchone()
        if existing is not None and str(existing["dataset_digest"]) != manifest.dataset_digest:
            raise CaseWorkspaceError("manifest identity collision")
        db.execute(
            """
            INSERT OR IGNORE INTO manifests(manifest_id, dataset_digest, file_count, total_size_bytes, committed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                manifest.manifest_id,
                manifest.dataset_digest,
                manifest.file_count,
                manifest.total_size_bytes,
                timestamp,
            ),
        )
        for entry, descriptor, stored_path in zip(
            manifest.entries, committed.source_descriptors, stored_paths, strict=False
        ):
            db.execute(
                """
                INSERT OR REPLACE INTO artifacts(
                    artifact_id, manifest_id, logical_path, sha256, size_bytes, media_type,
                    adapter_id, adapter_version, format_family, stored_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.artifact_id,
                    manifest.manifest_id,
                    entry.logical_path,
                    entry.sha256,
                    entry.size_bytes,
                    entry.media_type,
                    entry.adapter_id,
                    entry.adapter_version,
                    entry.format_family,
                    stored_path,
                ),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO sources(
                    source_id, manifest_id, source_kind, adapter_id, adapter_version, descriptor_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.source_id,
                    manifest.manifest_id,
                    descriptor.get("sourceKind"),
                    descriptor.get("adapterId"),
                    descriptor.get("adapterVersion"),
                    json.dumps(descriptor, sort_keys=True, separators=(",", ":")),
                ),
            )

    _atomic_json(manifest_path, payload)
    updated = CaseRecord(
        case_id=record.case_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=timestamp,
        schema_version=record.schema_version,
    )
    _atomic_json(root / "case.json", asdict(updated))
    return payload


def list_manifests(workspace_root: Path, case_id: str) -> tuple[dict[str, Any], ...]:
    root = case_path(workspace_root, case_id)
    load_case(workspace_root, case_id)
    with _connect(root / "case.db") as db:
        rows = db.execute("""
            SELECT manifest_id, dataset_digest, file_count, total_size_bytes, committed_at
            FROM manifests ORDER BY committed_at DESC, manifest_id
            """).fetchall()
    return tuple(dict(row) for row in rows)


def evidence_inventory(workspace_root: Path, case_id: str) -> tuple[dict[str, Any], ...]:
    root = case_path(workspace_root, case_id)
    load_case(workspace_root, case_id)
    with _connect(root / "case.db") as db:
        rows = db.execute("""
            SELECT artifact_id, manifest_id, logical_path, sha256, size_bytes, media_type,
                   adapter_id, adapter_version, format_family, stored_path
            FROM artifacts ORDER BY logical_path, artifact_id
            """).fetchall()
    return tuple(dict(row) for row in rows)


def case_artifact_rows(workspace_root: Path, case_id: str) -> tuple[dict[str, Any], ...]:
    """Committed artifacts joined with their manifest commit timestamp.

    Consumers rehydrate immutable bytes from ``stored_path``; ``committed_at``
    is the recorded intake time used as the analysis ``ingested_at`` value.
    """
    root = case_path(workspace_root, case_id)
    load_case(workspace_root, case_id)
    with _connect(root / "case.db") as db:
        rows = db.execute("""
            SELECT a.artifact_id, a.manifest_id, a.logical_path, a.sha256, a.size_bytes,
                   a.media_type, a.adapter_id, a.adapter_version, a.format_family,
                   a.stored_path, m.committed_at
            FROM artifacts a
            JOIN manifests m ON m.manifest_id = a.manifest_id
            ORDER BY a.logical_path, a.artifact_id
            """).fetchall()
    return tuple(dict(row) for row in rows)


def read_case_artifact(workspace_root: Path, case_id: str, row: Mapping[str, Any]) -> bytes:
    """Return immutable committed bytes for one ``case_artifact_rows`` row.

    Fails closed when stored bytes no longer match the recorded digest.
    """
    root = case_path(workspace_root, case_id)
    stored = root / str(row["stored_path"])
    content = stored.read_bytes()
    if hashlib.sha256(content).hexdigest() != str(row["sha256"]):
        raise CaseWorkspaceError(f"stored artifact digest mismatch: {row['artifact_id']}")
    return content


def save_case_output(
    workspace_root: Path, case_id: str, *, name: str, payload: dict[str, Any]
) -> Path:
    """Persist a derived deterministic output (analysis/report) under reports/."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name):
        raise CaseWorkspaceError(f"invalid case output name: {name!r}")
    root = case_path(workspace_root, case_id)
    load_case(workspace_root, case_id)
    path = root / "reports" / f"{name}.json"
    _atomic_json(path, payload)
    return path


def load_case_output(workspace_root: Path, case_id: str, *, name: str) -> dict[str, Any] | None:
    """Read a previously saved derived output, or None when absent."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name):
        raise CaseWorkspaceError(f"invalid case output name: {name!r}")
    root = case_path(workspace_root, case_id)
    load_case(workspace_root, case_id)
    path = root / "reports" / f"{name}.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def list_case_output_names(
    workspace_root: Path, case_id: str, *, prefix: str = ""
) -> tuple[str, ...]:
    """List saved derived-output names (``.stem``) under reports/, sorted."""
    root = case_path(workspace_root, case_id)
    load_case(workspace_root, case_id)
    reports = root / "reports"
    if not reports.is_dir():
        return ()
    return tuple(
        sorted(path.stem for path in reports.glob("*.json") if path.stem.startswith(prefix))
    )
