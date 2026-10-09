#!/usr/bin/env python3
"""Read-only first-party reproduction checks for the v7a0bb5f3 evidence package.

Requires only Python 3.10+ stdlib, a clean checkout and unmodified frozen inputs.
Does not invoke agents, AWS, HAIEC APIs, judge scoring or the organizer platform.
This is NOT independent native-source attestation or evidence of organizer receipt.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MANIFEST_COUNT = 506


def fail(message: str) -> None:
    raise AssertionError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def verify_manifest() -> None:
    entries: dict[str, str] = {}
    for line in (ROOT / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "Malformed MANIFEST.sha256 entry")
        expected, name = match.groups()
        require(name not in entries, "Duplicate manifest path: " + name)
        require(not name.startswith("/") and ".." not in Path(name).parts,
                "Unsafe manifest path: " + name)
        entries[name] = expected
    require(len(entries) == EXPECTED_MANIFEST_COUNT, "Manifest count mismatch")
    for name, expected in entries.items():
        path = ROOT / name
        require(path.is_file(), "Missing payload: " + name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == expected, "SHA-256 mismatch: " + name)
    print("MANIFEST: 506/506 byte-exact hashes PASS")


def verify_c16() -> None:
    cap = 60_000
    cases = (
        ("fault-1791167110-5e3126", 8, 35_559, "SATISFIED"),
        ("fault-1791165466-51ab52", 17, 106_829, "NOT_SATISFIED"),
    )
    for run, calls, reported, verdict in cases:
        obj = load_json("evidence/" + run + ".c16.bundle.json")
        require(obj["runId"] == run, "C16 run identity mismatch")
        m = obj["measurements"]["ACN-COST-001"]
        records = [x for x in m["usageRecords"] if x.get("contributesToActual")]
        require(len(records) == calls, "C16 executed-call count mismatch")
        require(all(x.get("executionState") == "PROVIDER_EXECUTED" and
                    x.get("usageQualification") == "QUALIFIED" for x in records),
                "C16 usage source qualification mismatch")
        input_sum = sum(int(x["inputTokens"]) for x in records)
        output_sum = sum(int(x["outputTokens"]) for x in records)
        measured = input_sum + output_sum
        require(measured == reported == m["actualRunTokens"], "C16 totals mismatch")
        require(m["providerExecutedCalls"] == calls, "C16 call ledger mismatch")
        agents = {x["agentId"] for x in records}
        require(agents == set(m["expectedAgentIds"]), "C16 expected agent coverage mismatch")
        actual_verdict = "SATISFIED" if measured <= cap else "NOT_SATISFIED"
        require(actual_verdict == verdict, "C16 recomputed verdict mismatch")
        print(f"C16 {run}: {calls} executed calls, {measured:,}/{cap:,}; {actual_verdict} (normalized records)")


def verify_original_c9() -> None:
    runs = ("fault-1791183079-256a5e", "fault-1791183213-228329")
    for run in runs:
        obj = load_json("evidence/judgment-day/c9-bundle-" + run + ".json")
        require(obj["runId"] == run, "C9 run identity mismatch")
        m = obj["measurements"]["AIA-ARC-006"]
        require(m["metricId"] == "aws.bedrock-agentcore.duration_ms", "C9 metric mismatch")
        require(m["direction"] == "LOWER_IS_BETTER", "C9 metric direction mismatch")
        require(m["baselineMode"] == "MATCHED_WINDOWS", "C9 baseline mode mismatch")
        windows = m["windows"]
        require(len(windows) == 3, "C9 expected three comparable windows")
        breaches = 0
        for window in windows:
            require(window["comparisonState"] == "COMPARABLE", "C9 window not comparable")
            baseline, live = window["baselineValue"], window["liveValue"]
            require(baseline > 0, "C9 zero baseline unsupported")
            recomputed = (live - baseline) / baseline
            reported = window["relativeDegradation"]
            require(abs(recomputed - reported) < 1e-9, "C9 normalized arithmetic mismatch")
            breaches += int(recomputed > 1.0)  # D=100%; B9=0%; strict violation when > D.
        require(breaches == 0, "Original C9 archived nonbreach result changed")
        print(f"C9 original {run}: {breaches}/3 windows violate D=100%; SATISFIED (normalized records)")
    print("C9 NOTE: later 44f/13c participant-system BREACH is NOT in this original archive")


def verify_known_limits() -> None:
    register = (ROOT / "register.yaml").read_text(encoding="utf-8")
    matrix = (ROOT / "evidence/judgment-day/TMF_DETECTION_COVERAGE_MATRIX.md").read_text(encoding="utf-8")
    require("id: AIA-ARC-004" in register and "C7 (AIA-LOG-001)" in matrix,
            "C7 identifier conflict changed; review source attribution")
    require("9/10" in matrix and "NEGOTIATION" in matrix, "C7 gap source missing")
    run_ids = (ROOT / "run-ids.txt").read_text(encoding="utf-8")
    s2 = [line for line in run_ids.splitlines()
          if "SCENARIO_S2" in line and "5/10 FAIL" in line]
    require(len(s2) == 2, "S2 original/retest source status mismatch")
    print("C7: original 9/10 NOT_SATISFIED; conflicting source catalog IDs identified (not silently repaired)")
    print("S2: original and retest 5/10 FAIL (source-register consistency; not grader replay)")
    print("SCOPE: SHA checks prove bytes; measurement checks use archived normalized values.")
    print("SCOPE: no organizer receipt, native AWS attestation, full C7 raw replay, or Delegation closure.")


def main() -> int:
    try:
        verify_manifest()
        verify_c16()
        verify_original_c9()
        verify_known_limits()
        print("VERIFICATION: PASS within the bounded checks specified above")
        return 0
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as error:
        print("VERIFICATION: FAIL — " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
