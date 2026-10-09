#!/usr/bin/env python3
"""Load the preserved TM Forum event evidence into a LogSense workspace.

Deterministic: analysis run IDs derive from artifact content digests, so the
generated workspace is reproducible on any machine at the same code commit.
Creates one case per judge-facing evidence grouping; no sample/demo case is
created or selected.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

BUNDLE = Path(os.environ.get("LOGSENSE_EVENT_HOME", ".")).resolve()
WORKSPACE = Path(os.environ["LOGSENSE_WORKSPACE"]).resolve()

# case_id -> (title, run dirs / files)
CASES = {
    "tmf-c16-pass":     ("C16 PASS — 35,559/60,000 tokens", ["fault-1791167110-5e3126"]),
    "tmf-c16-breach":   ("C16 BREACH — 106,829/60,000 tokens", ["fault-1791165466-51ab52"]),
    "tmf-c7-coverage":  ("C7 — 9/10 coverage, NEGOTIATION absent", ["fault-1791167110-5e3126"]),
    "tmf-s1":           ("S1 baseline-equivalent", ["fault-1791164605-3348a2"]),
    "tmf-s2-original":  ("S2 ambiguous — false certainty (original)", ["fault-1791190160-cb83f9"]),
    "tmf-s2-retest":    ("S2 retest — identical failure", ["fault-1791190812-668d63"]),
    "tmf-s3":           ("S3 restricted — safe refusal", ["fault-1791179120-30b2dc"]),
    "tmf-sec02-runaway":("SEC-02 runaway — 2.83M tokens, token-ceiling anomaly", ["fault-1791164066-bdd7e3"]),
    "tmf-enforcement":  ("Model/tool enforcement — runtime DENY", ["fault-1791164732-1092c5"]),
    "tmf-calibration":  ("Pre-freeze healthy calibration runs", [
        "fault-1791160393-344490", "fault-1791160491-d961be", "fault-1791160617-59b8bc"]),
    "tmf-killswitch":   ("Organizer-native ModelConfig kill switch", ["killswitch-1791200427"]),
}


def files_for(dirs):
    out = []
    for d in dirs:
        root = BUNDLE / "event-evidence" / "runs" / d
        if not root.is_dir():
            raise SystemExit(f"missing evidence dir: {root}")
        for f in sorted(root.iterdir()):
            if f.is_file():
                out.append(f)
    return out


def main() -> int:
    from logsense.integrations.service import IntegrationService

    service = IntegrationService(workspace_root=WORKSPACE)
    existing = {c["caseId"] for c in service.list_cases()}
    for cid, (title, dirs) in CASES.items():
        files = files_for(dirs)
        payload = [
            {"name": f"{f.parent.name}/{f.name}",
             "contentBase64": base64.b64encode(f.read_bytes()).decode("ascii")}
            for f in files
        ]
        if cid not in existing:
            try:
                service.create_case(case_id=cid, title=title)
            except Exception as exc:
                if "exists" not in str(exc).lower():
                    raise
        service.import_evidence({"caseId": cid, "files": payload})
        result = service.analyze_case(case_id=cid)
        findings = len(result["analysis"].get("findings", []) or [])
        print(f"{cid}: {len(files)} artifacts committed; analysis saved; findings={findings}")
    print(f"workspace ready: {WORKSPACE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
