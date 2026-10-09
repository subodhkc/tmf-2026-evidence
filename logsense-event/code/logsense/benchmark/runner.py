from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from logsense.benchmark.fixture_validation import (
    PHASE8_8_ASSERTION_TYPES,
    validate_assertion_shape,
    verify_artifact,
)

PHASE6_ASSERTION_TYPES = frozenset({
    "ACTION_PHASE_STATE",
    "CAUSE_STATE",
    "DETECTION_NOT_CAUSE",
    "DIVERGENCE_TYPE",
    "FIRST_DIVERGENCE_NOT_ROOT_CAUSE",
    "FORENSIC_TEST_RESULT",
    "INDEPENDENT_LINEAGE_COUNT",
    "MUST_NOT_CONFUSE",
    "MUST_NOT_EMIT_CAUSE",
    "MUST_NOT_EMIT_RELATION",
    "MUST_NOT_LABEL",
    "MUST_NOT_UPGRADE",
    "MUST_NOT_USE_EVIDENCE_AS",
    "MUST_PREFER_INSUFFICIENT_OVER_FALSE_CAUSE",
    "MUST_PRESERVE_UNKNOWN",
    "NATIVE_TIMESTAMP_PRESERVED",
    "NO_FALSE_IDENTITY_MERGE",
    "RELATION_MAX_STATE",
    "RELATION_STATE",
    "TEMPORAL_ALIGNMENT",
})

EXPECTED_CASE_IDS = tuple(f"GFB-{number:03d}" for number in range(1, 18))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_phase6_assertion(assertion: dict) -> list[str]:
    errors: list[str] = []
    if assertion.get("type") not in PHASE6_ASSERTION_TYPES:
        errors.append("UNKNOWN_PHASE6_ASSERTION_TYPE")
    if not assertion.get("assertionId"):
        errors.append("MISSING_ASSERTION_ID")
    if not assertion.get("target"):
        errors.append("MISSING_ASSERTION_TARGET")
    if not isinstance(assertion.get("critical"), bool):
        errors.append("CRITICAL_MUST_BE_BOOLEAN")
    return errors


def validate_case(case_dir: Path, dialect: str) -> tuple[list[str], int]:
    errors: list[str] = []
    case = load_json(case_dir / "case.json")
    case_id = case_dir.name
    if case.get("benchmarkId") != case_id:
        errors.append("CASE_ID_MISMATCH")

    for artifact in case.get("artifacts", []):
        for error in verify_artifact(
            case_dir / artifact["path"],
            artifact["sha256"],
            artifact["sizeBytes"],
        ):
            errors.append(f"{artifact['path']}:{error}")

    for rel in case.get("expectedObjectFiles", {}).values():
        path = case_dir / rel
        if not path.exists():
            errors.append(f"{rel}:MISSING_EXPECTED_OBJECT")
            continue
        if not isinstance(load_json(path), list):
            errors.append(f"{rel}:EXPECTED_OBJECT_MUST_BE_LIST")

    assertions = load_json(case_dir / "expected" / "assertions.json")
    critical_count = 0
    for assertion in assertions:
        if assertion.get("critical") is True:
            critical_count += 1
        if dialect == "PHASE6":
            assertion_errors = validate_phase6_assertion(assertion)
        elif dialect == "PHASE8_8":
            assertion_errors = validate_assertion_shape(assertion)
        else:
            assertion_errors = ["UNKNOWN_ASSERTION_DIALECT"]
        errors.extend(f"{assertion.get('assertionId', '?')}:{error}" for error in assertion_errors)

    if critical_count == 0:
        errors.append("MISSING_CRITICAL_ASSERTION")
    if dialect == "PHASE8_8" and not any(
        assertion.get("type") == "MUST_NOT_PROMOTE" and assertion.get("critical") is True
        for assertion in assertions
    ):
        errors.append("MISSING_CRITICAL_MUST_NOT_PROMOTE")

    return errors, critical_count


def run_fixture_gate(repo_root: Path) -> dict:
    manifest = load_json(repo_root / "fixtures" / "golden" / "manifest.json")
    failures: list[str] = []
    case_ids = [item["benchmarkId"] for item in manifest.get("cases", [])]
    if tuple(case_ids) != EXPECTED_CASE_IDS:
        failures.append("CASE_RANGE_MISMATCH")
    if manifest.get("caseCount") != 17:
        failures.append("CASE_COUNT_MISMATCH")
    if manifest.get("gateKind") != "FIXTURE_TRUTH_INTEGRITY":
        failures.append("GATE_KIND_MISMATCH")

    phase6 = set(manifest.get("assertionDialects", {}).get("PHASE6", {}).get("assertionTypes", []))
    phase88 = set(manifest.get("assertionDialects", {}).get("PHASE8_8", {}).get("assertionTypes", []))
    if phase6 != PHASE6_ASSERTION_TYPES:
        failures.append("PHASE6_ASSERTION_VOCAB_MISMATCH")
    if phase88 != set(PHASE8_8_ASSERTION_TYPES):
        failures.append("PHASE8_8_ASSERTION_VOCAB_MISMATCH")

    metrics = manifest.get("zeroToleranceMetrics", {})
    if metrics != {
        "FALSE_CAUSAL_ATTRIBUTION_RATE": 0.0,
        "FALSE_ACTION_APPLIED_RATE": 0.0,
        "FALSE_IDENTITY_MERGE_RATE": 0.0,
        "FALSE_CORROBORATION_RATE": 0.0,
        "CRITICAL_HARD_NEGATIVE_PASS_RATE": 1.0,  # nosec B105  # benchmark metric key, not a credential
    }:
        failures.append("ZERO_TOLERANCE_METRICS_MISMATCH")

    critical_total = 0
    for item in manifest.get("cases", []):
        case_dir = repo_root / item["path"]
        if not case_dir.exists():
            failures.append(f"{item['benchmarkId']}:MISSING_CASE_DIRECTORY")
            continue
        case_errors, critical_count = validate_case(case_dir, item["assertionDialect"])
        critical_total += critical_count
        if critical_count != item["criticalAssertionCount"]:
            failures.append(f"{item['benchmarkId']}:CRITICAL_ASSERTION_COUNT_MISMATCH")
        failures.extend(f"{item['benchmarkId']}:{error}" for error in case_errors)

    return {
        "passed": not failures,
        "caseCount": len(case_ids),
        "criticalAssertionCount": critical_total,
        "failures": failures,
    }
