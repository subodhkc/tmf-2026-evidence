"""Immutable analysis snapshot store.

Every saved deterministic analysis becomes an immutable snapshot record under
``cases/<case>/snapshots/``. Re-running analysis after new evidence or mapping
changes writes a *new* snapshot; prior snapshots are never rewritten. A
pointer file records which snapshot is active so existing consumers of
``analysis``/``report`` keep working unchanged.

Cases analyzed before this store existed keep their flat ``analysis.json`` /
``report.json`` outputs — those are reported as ``LEGACY_ACTIVE_OUTPUT`` and
never get fabricated provenance fields.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from logsense.workspace.cases import case_path

SNAPSHOT_SCHEMA = "analysis-snapshot/0.1"
SNAPSHOT_STATES = (
    "CURRENT",
    "STALE_EVIDENCE_CHANGED",
    "STALE_MAPPING_CHANGED",
    "LEGACY_ACTIVE_OUTPUT",
    "NONE",
)

_SNAPSHOT_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _snapshots_dir(workspace_root: Path, case_id: str) -> Path:
    return case_path(workspace_root, case_id) / "snapshots"


def _pointer_path(workspace_root: Path, case_id: str) -> Path:
    return case_path(workspace_root, case_id) / "snapshots" / "active.json"


def _safe_name(snapshot_id: str) -> str:
    return _SNAPSHOT_ID_RE.sub("_", str(snapshot_id))[:120] or "snapshot"


def save_analysis_snapshot(
    workspace_root: Path,
    case_id: str,
    *,
    analysis: dict[str, Any],
    report: dict[str, Any] | None,
    mapping_profile_refs: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Persist one immutable analysis snapshot and mark it active.

    Returns the stored snapshot record (provenance metadata + payloads).
    """
    embedded = analysis.get("snapshot") or {}
    snapshot_id = str(embedded.get("snapshotId") or analysis.get("analysisRunId") or "snapshot")
    directory = _snapshots_dir(workspace_root, case_id)
    directory.mkdir(parents=True, exist_ok=True)
    sequence = len(list(directory.glob("snapshot-*.json"))) + 1
    record = {
        "schemaVersion": SNAPSHOT_SCHEMA,
        "snapshotId": snapshot_id,
        "snapshotLabel": f"A-{sequence:03d}",
        "snapshotDigest": embedded.get("digest"),
        "caseId": case_id,
        "analysisRunId": analysis.get("analysisRunId"),
        "evidenceSetRef": analysis.get("evidenceSetId"),
        "createdAt": embedded.get("createdAt") or analysis.get("createdAt"),
        "artifactRefs": [
            {"artifactId": row.get("artifactId"), "sha256": row.get("sha256")}
            for row in analysis.get("artifactResults") or ()
            if isinstance(row, dict) and row.get("artifactId")
        ],
        "artifactDigests": sorted(
            str(row["sha256"])
            for row in analysis.get("artifactResults") or ()
            if isinstance(row, dict) and row.get("sha256")
        ),
        "mappingProfileRefs": sorted(str(ref) for ref in (mapping_profile_refs or ()) if ref),
        "semanticProfileRefs": sorted(
            {
                str(pid)
                for row in analysis.get("artifactResults") or ()
                if isinstance(row, dict)
                for pid in (row.get("semanticProfileIds") or ())
            }
        ),
        "eventCount": len(analysis.get("canonicalEvents") or ()),
        "artifactCount": len(analysis.get("artifactResults") or ()),
        "limitations": sorted(set(limitations or ())),
        "analysis": analysis,
        "report": report,
    }
    path = directory / f"snapshot-{_safe_name(snapshot_id)}.json"
    if not path.exists():
        _atomic_json(path, record)
    _atomic_json(_pointer_path(workspace_root, case_id), {"snapshotId": snapshot_id})
    stored = dict(record)
    stored.pop("analysis", None)
    stored.pop("report", None)
    return stored


def list_analysis_snapshots(
    workspace_root: Path, case_id: str
) -> list[dict[str, Any]]:
    """List snapshot metadata rows (payloads omitted), oldest first."""
    directory = _snapshots_dir(workspace_root, case_id)
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("snapshot-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        record.pop("analysis", None)
        record.pop("report", None)
        rows.append(record)
    # Label carries the creation sequence (A-001, A-002 …) — filenames are
    # content-derived and do not sort chronologically.
    rows.sort(key=lambda row: str(row.get("snapshotLabel") or ""))
    return rows


def load_analysis_snapshot(
    workspace_root: Path, case_id: str, snapshot_id: str
) -> dict[str, Any] | None:
    """Load a full snapshot record (analysis + report payloads)."""
    path = _snapshots_dir(workspace_root, case_id) / f"snapshot-{_safe_name(snapshot_id)}.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def active_snapshot_id(workspace_root: Path, case_id: str) -> str | None:
    path = _pointer_path(workspace_root, case_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    snapshot_id = str(value.get("snapshotId") or "")
    return snapshot_id or None


def set_active_snapshot(workspace_root: Path, case_id: str, snapshot_id: str) -> dict[str, Any]:
    """Repoint the active snapshot. The snapshot must exist; it is never modified."""
    record = load_analysis_snapshot(workspace_root, case_id, snapshot_id)
    if record is None:
        raise KeyError(f"analysis snapshot not found: {snapshot_id}")
    _atomic_json(_pointer_path(workspace_root, case_id), {"snapshotId": snapshot_id})
    return record
