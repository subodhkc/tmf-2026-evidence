"""Bundled deterministic competition fixtures.

Two fixture packs ship with the package so an operator can exercise the full
Control 7 path end-to-end before pointing it at real run evidence:

- ``control7-healthy`` — 10 required expected events, all observed and
  matched in order, all timing gaps measurable and inside the declared
  limit.
- ``control7-breach`` — 10 expected events, one authorization event not
  observed (9 matched / 90% coverage) and one consecutive-event gap that
  exceeds the declared limit.

These are measurement fixtures only — they carry no PASS/FAIL label. The
fixture evidence is ordinary JSONL shaped so the canonical intake selects
``sem.agent-action.v1`` and emits exactly one schema-compatible mapping
proposal; loading a fixture binds that proposal through the standard
``approvalMode: USER`` runtime path with fixture provenance recorded.

Run-activity coverage: ``control7-healthy``, ``control9-healthy`` and
``control16-pass`` each carry one explicit ``RUN_STARTED`` lifecycle record
(qualified run-start evidence — ``runActivity.startState == ESTABLISHED``).
All other fixtures demonstrate the fail-closed ``NOT_ESTABLISHED`` state:
event/KPI/call timestamps alone never establish ``runStartedAt``.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from logsense.competition.expected_events import normalize_manifest
from logsense.competition.run import normalize_run_declaration

FIXTURE_PACKAGE = "logsense.competition.fixtures"

COMPETITION_FIXTURES = (
    "control7-healthy",
    "control7-breach",
    "control16-pass",
    "control16-retry-storm",
    "control16-evidence-failure",
    "control16-pending",
    "control16-denied",
    "control9-official",
    "control9-healthy",
    "control9-partial",
    "control9-latency",
    "control9-incompatible",
    "control9-zero-baseline",
)


class CompetitionFixtureError(ValueError):
    """Raised for unknown or malformed competition fixtures."""


def fixture_names() -> tuple[str, ...]:
    return COMPETITION_FIXTURES


def _fixture_root(name: str) -> Any:
    if name not in COMPETITION_FIXTURES:
        raise CompetitionFixtureError(
            f"unknown competition fixture: {name} (available: {', '.join(COMPETITION_FIXTURES)})"
        )
    return files(FIXTURE_PACKAGE).joinpath(name)


def fixture_meta(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        _fixture_root(name).joinpath("meta.json").read_text(encoding="utf-8")
    )
    return payload


def list_fixtures() -> list[dict[str, Any]]:
    return [fixture_meta(name) for name in COMPETITION_FIXTURES]


def load_fixture(name: str) -> dict[str, Any]:
    """Return the fixture pack: meta, run declaration, manifest, evidence."""
    root = _fixture_root(name)
    meta = fixture_meta(name)
    run = normalize_run_declaration(
        json.loads(root.joinpath(meta["runFile"]).read_text(encoding="utf-8"))
    )
    # C16 reconciliation fixtures carry no expected-event manifest — the
    # Control 16 surface reconciles observed usage, not declared events.
    manifest = (
        normalize_manifest(
            json.loads(root.joinpath(meta["manifestFile"]).read_text(encoding="utf-8"))
        )
        if meta.get("manifestFile")
        else None
    )
    evidence: dict[str, bytes] = {}
    for file_name in meta["evidenceFiles"]:
        evidence[file_name] = root.joinpath("evidence", file_name).read_bytes()
    return {
        "fixtureId": name,
        "meta": meta,
        "runDeclaration": run,
        "expectedManifest": manifest,
        "evidence": evidence,
    }


def fixture_paths_for_tests(name: str, destination: Path) -> list[Path]:
    """Materialize fixture evidence under a real directory (test helper)."""
    fixture = load_fixture(name)
    written: list[Path] = []
    for file_name, content in fixture["evidence"].items():
        target = destination / file_name
        target.write_bytes(content)
        written.append(target)
    return written
