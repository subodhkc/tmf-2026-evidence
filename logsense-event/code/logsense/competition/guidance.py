"""Structured TM Forum competition guidance — the single content owner.

The UI, the AI competition-guide context, and the operator docs all consume
this module so event copy does not drift into three conflicting versions.
Everything here is *guidance*: it teaches the event workflow and readiness
criteria. It never carries forensic truth — deterministic projections own
that — and it never contains a HAIEC verdict.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

GUIDANCE_SCHEMA = "competition-guidance/0.1"

# --------------------------------------------------------------------------
# Capability truth — update these flags when the HAIEC side ships; copy
# everywhere else derives from here.
# --------------------------------------------------------------------------

# Technical capability and event status are separate columns and must never
# be merged. AVAILABLE != EVENT ASSESSED — event assessment requires real
# event evidence bound through the HAIEC frozen Event Freeze / scored-set
# path. Fixture/synthetic results prove the mechanism only.
HAIEC_EVENT_FOOTNOTE = (
    "* NOT YET — AVAILABLE != EVENT ASSESSED. Event assessment requires real "
    "event evidence bound through the HAIEC frozen Event Freeze / "
    "scored-set path; fixture or rehearsal results never satisfy it."
)

CAPABILITY_TRUTH: dict[str, Any] = {
    "controls": [
        {
            "controlNumber": 7,
            "controlCode": "AIA-LOG-001",
            "name": "Event Recording",
            "logsenseMeasurement": "AVAILABLE",
            "haiecControlTest": "AVAILABLE",
            "eventAssessed": "NOT_YET",
        },
        {
            "controlNumber": 9,
            "controlCode": "AIA-ARC-006",
            "name": "Drift & Performance",
            "logsenseMeasurement": "AVAILABLE",
            "haiecControlTest": "AVAILABLE",
            "eventAssessed": "NOT_YET",
        },
        {
            "controlNumber": 16,
            "controlCode": "ACN-COST-001",
            "name": "Agent Spend Cap",
            "logsenseMeasurement": "AVAILABLE",
            "haiecControlTest": "AVAILABLE",
            "eventAssessed": "NOT_YET",
        },
    ],
    "footnote": HAIEC_EVENT_FOOTNOTE,
    "hardBoundary": (
        "LogSense measurement is not a HAIEC verdict. HAIEC owns the control "
        "register, frozen versions, thresholds, baselines, budgets and the "
        "final SATISFIED / NOT_SATISFIED Control Test."
    ),
}

# Aligned with the HAIEC judge/operator vocabulary (Assurance Lab #2071/#2072).
# Technical capability is not event status; the governing rule for an event
# run is the Frozen Event Governing Instance — the event-specific policy
# record — never the generic reusable control definition.
CONCEPT_VOCABULARY: dict[str, Any] = {
    "technicalCapability": (
        "TECHNICAL PATH AVAILABLE — LogSense can measure and HAIEC can "
        "evaluate. Says nothing about whether an assessed event run occurred."
    ),
    "eventStatus": (
        "EVENT ASSESSED: NOT YET — until real event evidence exists. Only a "
        "persisted FROZEN Event Freeze binding in HAIEC establishes an "
        "assessed run; fixture/synthetic results never qualify."
    ),
    "governingRule": (
        "Frozen Event Governing Instance — the event-specific HAIEC policy "
        "record carrying the actual thresholds/baseline/budget for this "
        "event. REUSABLE CONTROL != EVENT GOVERNING INSTANCE: the library "
        "control definition does not contain the event's real numbers."
    ),
    "runtimeVsScored": (
        "Runtime evaluator answers 'is this action allowed now?' — live "
        "allow/deny at an enforcement point. Control Test answers 'did this "
        "control hold for this declared run/window?' — post-run deterministic "
        "assessment. LogSense normally feeds the latter; a LogSense "
        "measurement is never runtime enforcement."
    ),
}

# --------------------------------------------------------------------------
# Event orientation
# --------------------------------------------------------------------------

EVENT_MISSION: dict[str, Any] = {
    "headline": (
        "The lab already provides the AI system and the collaborating agents. "
        "You are not being asked to build the agents."
    ),
    "mission": (
        "Your job is to build controls around the supplied system and to prove, "
        "independently, whether those controls held. LogSense is your forensic "
        "workbench: it preserves raw evidence, reconstructs what actually ran, "
        "measures Controls 7/9/16 deterministically, and hands evidence to "
        "HAIEC, which owns the final Control Test verdict."
    ),
}

LAB_SHAPE: dict[str, Any] = {
    "caveat": (
        "This is the expected architecture shape. Actual workshop payloads, "
        "field names, APIs and source semantics must be discovered from the "
        "live lab — never assumed."
    ),
    "zones": [
        {
            "zone": "Customer Zone",
            "components": ["Chat agent", "Trouble ticket / ServiceNow"],
        },
        {"zone": "— Gateway A —", "components": []},
        {
            "zone": "IT Zone",
            "components": ["Triage agent", "Account records", "AWS"],
        },
        {"zone": "— Gateway B —", "components": []},
        {
            "zone": "Network Zone",
            "components": ["Investigation agent", "Network inventory", "Digital twin", "AWS / NVIDIA"],
        },
    ],
    "shared": "Shared Model Gateway — used by model calls across all zones.",
    "supporting": [
        "OTel collector / storage",
        "Digital twin",
        "Scenario / fault switch",
        "Sandboxes",
        "Credentials",
    ],
}

THREE_LAYERS: list[dict[str, Any]] = [
    {
        "layer": "Layer 1 — Supplied Runtime",
        "contains": [
            "AI agents",
            "gateways",
            "shared model gateway",
            "telemetry",
            "digital twin",
            "scenario controls",
        ],
        "question": "What system is running?",
    },
    {
        "layer": "Layer 2 — LogSense",
        "contains": ["preserve", "map", "reconstruct", "measure", "explain evidence"],
        "question": "What actually happened?",
    },
    {
        "layer": "Layer 3 — HAIEC",
        "contains": [
            "freeze policy",
            "evaluate measurement",
            "bind result",
            "answer Control Test",
        ],
        "question": "What rule governed it, and did it hold?",
    },
]

ORGANIZER_ARCHITECTURE: dict[str, Any] = {
    "flow": "AI System → Enforcement Point(s) → Telemetry  |  Control Register, Evaluator, Evidence Ledger, Control Test / Query",
    "transports": [
        {"name": "evaluate()", "meaning": "synchronous / in-path check"},
        {"name": "emit()", "meaning": "asynchronous evidence production"},
        {"name": "callback()", "meaning": "deferred / human approval path"},
        {"name": "pull()", "meaning": "scheduled / continuous collection"},
    ],
    "habits": [
        "Telemetry store never judges.",
        "Evaluator never remembers.",
        "Control register is never the execution path.",
        "Evidence ledger never interprets.",
        "Evidence is bound to control / version / run where produced.",
    ],
}

# --------------------------------------------------------------------------
# Judging axes
# --------------------------------------------------------------------------

JUDGING_AXES: dict[str, Any] = {
    "axis1": {
        "name": "How many controls are complete (0–3)",
        "point": (
            "A control is not complete merely because LogSense can measure it."
        ),
        "completionChecklist": [
            "control selected",
            "metric / measurement defined",
            "governing policy frozen in HAIEC",
            "evidence available",
            "LogSense measurement",
            "HAIEC deterministic Control Test",
            "named intended-PASS run",
            "named intended-breach run",
            "same frozen policy on both runs",
            "openable evidence",
            "gaps documented",
            "judge rehearsal done",
        ],
    },
    "axis2": {
        "name": "Quality",
        "dimensions": [
            {
                "name": "LIVE TEST",
                "point": "A judge can name a control + run/window and get an answer quickly.",
            },
            {
                "name": "ARCHITECTURE",
                "point": "Decision, policy, evidence and execution/enforcement responsibilities are separated.",
            },
            {
                "name": "EVIDENCE",
                "point": "Records are bound to control, version, run/window and measurement — and can be opened independently.",
            },
            {
                "name": "HONESTY",
                "point": "Gaps stay visible; insufficient evidence never becomes green. One honest failure beats a fake all-green.",
            },
        ],
        "note": "Readiness guidance only — no judging score is assigned.",
    },
    "axis3": {
        "name": "Bonus",
        "paths": [
            "second completed control",
            "third completed control",
            "continuous / inline compliance",
            "adversarial testing",
            "second enforcement point",
        ],
        "guardrail": (
            "Do not spend bonus time while a core control remains incomplete "
            "or non-judgeable."
        ),
    },
}

ORGANIZER_SIX_STEPS: list[dict[str, Any]] = [
    {
        "step": 1,
        "stepText": "Choose your control(s).",
        "owner": "team decision + LogSense feasibility guidance",
    },
    {"step": 2, "stepText": "Declare your threshold ranges.", "owner": "HAIEC"},
    {
        "step": 3,
        "stepText": "Decide where/when the control is checked.",
        "owner": "team architecture decision",
    },
    {
        "step": 4,
        "stepText": "Build the control at the selected enforcement/check point.",
        "owner": "lab / HAIEC / enforcement integration depending on control",
    },
    {"step": 5, "stepText": "Build the control test/evaluator.", "owner": "HAIEC"},
    {
        "step": 6,
        "stepText": "Run it both ways and record the gaps.",
        "owner": "LogSense + HAIEC",
    },
]

# --------------------------------------------------------------------------
# First-hour discovery artifacts
# --------------------------------------------------------------------------

FIRST_HOUR_ARTIFACTS: dict[str, Any] = {
    "sourceInventory": {
        "name": "Source Inventory",
        "fields": [
            "source name",
            "producer",
            "format",
            "access/export path",
            "sample captured?",
            "what it may prove",
            "candidate controls",
            "known gaps",
            "adapter needed?",
        ],
    },
    "runIdMap": {
        "name": "Run-ID Map",
        "fields": [
            "runId",
            "scenarioRunId",
            "traceId",
            "requestId",
            "sessionId",
            "actionCorrelationId",
            "taskId",
            "toolCallId",
            "mcpCallId",
            "modelCallId",
            "providerRequestId",
        ],
    },
    "enforcementPointMap": {
        "name": "Enforcement-Point Map",
        "fields": [
            "point (e.g. Gateway A, Gateway B, Shared Model Gateway, other discovered)",
            "what passes through it",
            "which control might use it",
            "can observe?",
            "can refuse?",
            "telemetry emitted?",
        ],
    },
    "metricInventory": {
        "name": "Metric Inventory",
        "perControl": {
            "AIA-LOG-001": [
                "event identity",
                "event type",
                "actor/agent",
                "operation",
                "timestamps",
                "expected-event source",
            ],
            "AIA-ARC-006": [
                "metric",
                "numeric value field",
                "unit",
                "direction",
                "scope",
                "window/cadence",
                "aggregation",
                "baseline candidate",
            ],
            "ACN-COST-001": [
                "agent",
                "model call ID",
                "provider request ID",
                "input tokens",
                "output tokens",
                "retry/attempt",
                "execution/finality semantics",
            ],
        },
    },
    "scenarioRunMap": {
        "name": "Scenario / Run Map",
        "fields": [
            "calibration / known-good",
            "assessed-pass candidate",
            "assessed-breach candidate",
            "retest",
            "scenario/fault ID",
        ],
        "note": "Reuse the Run Manager — do not build a parallel run system.",
    },
    "clockIntegrity": {
        "name": "Time / Clock Integrity",
        "perSource": [
            "UTC or local timestamps",
            "authoritative clock source",
            "synchronized infrastructure clock",
            "timestamp precision",
            "expected cross-system skew",
        ],
        "systems": [
            "ServiceNow",
            "AgentCore / AWS",
            "OTel / CloudWatch",
            "model gateway",
            "Digital Twin / KPI source",
        ],
        "note": (
            "A timing comparison cannot be treated as authoritative merely "
            "because two timestamps parse. No skew correction is invented — "
            "if clock comparability cannot be established, it is surfaced "
            "as a limitation/gap."
        ),
    },
}

# The operator first-hour path — compressed to four windows matching the
# actual event sequence. Ordering matters: connect before identity, identity
# before control facts, facts before qualification.
FIRST_HOUR_SEQUENCE: list[dict[str, Any]] = [
    {
        "window": "0–15 min",
        "phase": "CONNECT / INVENTORY",
        "identify": [
            "ServiceNow AICT / Agent Studio",
            "AWS / AgentCore",
            "model gateway",
            "OTel / CloudWatch",
            "Digital Twin / KPI",
            "scenario / run source",
            "HAIEC connectivity",
        ],
        "capture": "One representative record from each real source.",
    },
    {
        "window": "15–30 min",
        "phase": "RUN IDENTITY",
        "identify": [
            "runId",
            "correlation / trace IDs",
            "cross-system join keys",
            "explicit RUN_START / ASSESSED_ACTIVITY_START",
            "enforcement-point references",
        ],
        "capture": (
            "Explicit qualified run-start evidence only — declaration time, "
            "earliest observed activity and timestamp proximity never qualify."
        ),
    },
    {
        "window": "30–45 min",
        "phase": "CONTROL FACTS",
        "perControl": {
            "AIA-LOG-001": ["expected events", "event identity/order", "timing/gap fields"],
            "AIA-ARC-006": ["KPI", "unit", "direction", "baseline", "comparable-window semantics"],
            "ACN-COST-001": ["call ID", "input tokens", "output tokens", "retry identity", "agent/model identity"],
        },
        "capture": "Exact field names per control — never assume semantics.",
    },
    {
        "window": "45–60 min",
        "phase": "QUALIFY",
        "identify": [
            "approve deterministic source mappings",
            "resolve READY / LIMITED / BLOCKED / ONSITE_VERIFY per scored control",
        ],
        "capture": (
            "A source is never QUALIFIED because its field names merely look "
            "plausible — only run-bound qualified evidence earns QUALIFIED."
        ),
    },
]

# When the sanctioned environment cannot reach HAIEC synchronously this is
# not an event failure — the post-run path is the scored path.
OPERATOR_FALLBACK = (
    "If sanctioned AWS/ServiceNow cannot call HAIEC synchronously, that is "
    "NOT an event failure. The fallback path is: runtime evidence → "
    "LogSense collection/reconstruction → Competition Evidence Bundle → "
    "HAIEC post-run Control Test. Inline/live C16 enforcement remains bonus "
    "capability only when a real defensible hook exists — never simulate "
    "inline enforcement to improve the demo story."
)

# The judge-readiness bar for a LogSense evidence bundle — an evidence
# portability test, not a HAIEC verdict test.
SKEPTICAL_STRANGER_CHECK: dict[str, Any] = {
    "title": "SKEPTICAL STRANGER CHECK — evidence portability",
    "intro": (
        "Before declaring an evidence bundle judge-ready, another operator "
        "should be able to determine, without verbal explanation:"
    ),
    "items": [
        "which run this is",
        "which control it measures",
        "the measurement result/value",
        "the exact evidence references",
        "the source / mapping identity",
        "the known gaps / limitations",
    ],
    "note": (
        "This is not a HAIEC verdict test — it is an "
        "evidence-portability/readability test over the LogSense bundle."
    ),
}

# Judge/operator query routing — two different questions, two different
# owners. LogSense answers "what happened"; HAIEC answers "did it hold".
QUERY_ROUTING: dict[str, Any] = {
    "title": "ASK TWO DIFFERENT QUESTIONS",
    "whatHappened": {
        "question": "What happened?",
        "use": "LogSense Timeline / Forensic Window",
        "returns": [
            "events/actions",
            "calls",
            "KPI changes",
            "sources",
            "evidence refs",
            "gaps",
        ],
        "verdict": "NO VERDICT",
    },
    "didItHold": {
        "question": "Did the control hold?",
        "use": "HAIEC Control Test",
        "returns": [
            "reusable control",
            "Frozen Event Governing Instance",
            "run/window",
            "deterministic calculation",
            "SATISFIED / NOT_SATISFIED / NOT_EVALUATED",
            "exact evidence",
            "limitations/gaps",
        ],
    },
}

# Competition capability ladder — evidence-backed statuses only. The
# bounded vocabulary is AVAILABLE / READY FOR ONSITE / ONSITE VERIFY /
# DEMONSTRATED / BLOCKED / NOT YET. DEMONSTRATED is never inferred without
# evidence; a rehearsal measurement demonstrates the technical path, not
# an event assessment.
CAPABILITY_LADDER: dict[str, Any] = {
    "title": "COMPETITION CAPABILITY LADDER",
    "states": (
        "AVAILABLE",
        "READY_FOR_ONSITE",
        "ONSITE_VERIFY",
        "TECHNICALLY_PROVEN",
        "DEMONSTRATED",
        "BLOCKED",
        "NOT_YET",
    ),
    "layers": [
        {"layer": 1, "name": "One scored control completely end-to-end"},
        {"layer": 2, "name": "C7 + C9 + C16 complete"},
        {
            "layer": 3,
            "name": "Five-plane proof",
            "planes": [
                "REQUESTED",
                "POLICY_AUTHORIZED",
                "EFFECTIVELY_GRANTED",
                "CODE_CAPABLE",
                "OBSERVED",
            ],
        },
        {"layer": 4, "name": "ServiceNow human-governance proof"},
        {"layer": 5, "name": "Real-time C16"},
        {"layer": 6, "name": "Second real enforcement point"},
        {"layer": 7, "name": "Adversarial scenario"},
        {
            "layer": 8,
            "name": "Forensic time-window exploration + HAIEC deterministic Control Test",
        },
    ],
    "note": (
        "Statuses are evidence-backed only — a layer is never promoted on a "
        "plausible architecture or an operator's plan. Persisted "
        "rehearsal/fixture evidence earns TECHNICALLY_PROVEN; DEMONSTRATED "
        "requires explicit authoritative live-event provenance. "
        "REHEARSAL / SYNTHETIC != EVENT DEMONSTRATED."
    ),
}

# Enforcement-point readiness — a UI or MCP surface is never itself an
# enforcement point, and a second point counts only across a genuinely
# different operational boundary.
ENFORCEMENT_POINT_NOTE = (
    "UI / MCP != ENFORCEMENT POINT. A second enforcement point counts only "
    "when a genuinely different operational boundary is demonstrated. Likely "
    "event candidates — once proven — may include the Shared Model Gateway, "
    "the AgentCore tool boundary, a ServiceNow/human queue, or another actual "
    "gateway. None is pre-labeled as proven."
)

# Declared/authorized vs observed — the five evidence planes help the
# operator spot divergence; they never create a verdict.
PLANE_READINESS: dict[str, Any] = {
    "title": "DECLARED / AUTHORIZED vs OBSERVED",
    "planes": [
        {
            "plane": "REQUESTED",
            "potentialEvidence": ["ODA change/config request"],
        },
        {
            "plane": "POLICY_AUTHORIZED",
            "potentialEvidence": [
                "approved CR",
                "Cedar",
                "Guardrail",
                "approved model/tool configuration",
            ],
        },
        {
            "plane": "EFFECTIVELY_GRANTED",
            "potentialEvidence": [
                "IAM",
                "ACL",
                "AgentCore/gateway effective permission",
            ],
        },
        {
            "plane": "CODE_CAPABLE",
            "potentialEvidence": ["exact bound source/config scan if available"],
        },
        {
            "plane": "OBSERVED",
            "potentialEvidence": [
                "OTel",
                "gateway",
                "CloudWatch",
                "AICT/runtime evidence",
            ],
        },
    ],
    "note": (
        "Unknown planes remain UNKNOWN / NOT ESTABLISHED. This helps the "
        "operator spot divergence — it does not create a new verdict."
    ),
}

# ServiceNow human-loop readiness for C9 — silence is a governance fact,
# never upgraded into acknowledgement or remediation.
HUMAN_LOOP: dict[str, Any] = {
    "title": "ServiceNow human-loop readiness (C9)",
    "items": [
        {"key": "c9Measurement", "item": "C9 measurement available"},
        {"key": "haiecResult", "item": "HAIEC breach/control result established?"},
        {"key": "alertProduced", "item": "alert produced?", "terms": ("alert", "escalat", "ticket", "incident")},
        {"key": "namedHuman", "item": "named human/queue?", "terms": ("human", "queue", "assignee", "owner")},
        {"key": "ackReceived", "item": "acknowledgement received?", "terms": ("acknowledg", "ack")},
        {"key": "responseRecorded", "item": "response/action recorded?", "terms": ("response", "remediat", "action taken", "resolved")},
        {"key": "silenceRecorded", "item": "no response / silence recorded?", "terms": ("silence", "no response", "unanswered")},
        {"key": "evidenceRef", "item": "evidence ref available?"},
    ],
    "silenceRule": "SILENCE IS AN OBSERVED GOVERNANCE FACT",
    "note": (
        "Silence must never be converted into acknowledgement or "
        "remediation. LogSense establishes the drift measurement; HAIEC "
        "establishes whether the frozen C9 policy was satisfied. ServiceNow "
        "is not the C9 evaluator — HAIEC remains the deterministic Control "
        "Test owner."
    ),
}

# C16 runtime bonus — three distinct outcomes that must never be merged.
C16_RUNTIME_BONUS: dict[str, Any] = {
    "title": "C16 runtime bonus — prevention vs breach",
    "cases": [
        {
            "key": "withinCap",
            "name": "A — WITHIN CAP",
            "meaning": "Provider execution completes within the frozen run cap.",
        },
        {
            "key": "preventedAttempt",
            "name": "B — PREVENTED ATTEMPT",
            "meaning": (
                "A real enforcement point denies an attempted over-cap "
                "action. Strong preventive-control evidence — it is NOT an "
                "executed over-cap breach."
            ),
        },
        {
            "key": "executedBreach",
            "name": "C — EXECUTED BREACH",
            "meaning": (
                "Provider execution actually pushes the frozen run/accounting "
                "scope beyond the cap. The post-run breach case."
            ),
        },
    ],
    "neverClaim": (
        "Never claim atomic reservation, guaranteed no-overshoot, or "
        "real-time enforcement unless the live event gateway proves them."
    ),
}

# Evidence identity integrity — mirrored telemetry describing one action
# is not multiple actions; a genuine retry is not a duplicate observation.
EVIDENCE_IDENTITY: dict[str, Any] = {
    "title": "EVIDENCE IDENTITY INTEGRITY",
    "mirroring": (
        "OTel + CloudWatch + AICT + Gateway may describe the same underlying "
        "action. MULTIPLE RECORDS != MULTIPLE ACTIONS."
    ),
    "retryRule": (
        "Genuine provider retry != duplicate observation of the same call."
    ),
    "note": (
        "If canonical identity cannot establish equivalence, the gap is "
        "shown — no deduplication heuristic is applied."
    ),
}

# Source → deployment continuity — binds build/source identity to runtime
# identity only through evidence, never by assumption.
SOURCE_CONTINUITY: dict[str, Any] = {
    "title": "Source → deployment continuity",
    "githubPath": (
        "If GitHub source is available: repo → commit → build/deployment → "
        "AgentCore/ServiceNow runtime identity."
    ),
    "localPath": (
        "If local source/archive is available: snapshot/digest → HAIEC local "
        "scan → deployment/config identity → runtime identity."
    ),
    "noSource": "CODE_CAPABLE NOT ESTABLISHED",
    "fallback": (
        "With no bound source, rely on authorization / configuration / "
        "effective / runtime evidence."
    ),
    "neverImply": (
        "Never imply a copied/forked repository is the deployed organizer "
        "source without binding proof."
    ),
}

EVIDENCE_HUNTING: dict[str, list[str]] = {
    "Run identity": [
        "run IDs",
        "scenarioRunId",
        "trace IDs",
        "request IDs",
        "session IDs",
        "agentExecutionId",
        "action/tool/model call IDs",
        "fault/scenario ID",
    ],
    "Run start": [
        "RUN_STARTED / scenario-started event",
        "execution-started / fault-resolution-started record",
        "a field an approved mapping declares as RUN_START",
        "never: declaration time, first timestamp, KPI time",
    ],
    "Agent workflow": [
        "agent execution logs",
        "tool calls",
        "function calls",
        "MCP calls",
        "API transactions",
        "action/result records",
    ],
    "Policy / enforcement": [
        "authorization records",
        "guardrail decisions",
        "gateway decisions",
        "allow/deny/stop records",
        "enforcement-point identity (which gateway/proxy/boundary)",
        "customer-side / IT-side / network-side / shared-model-gateway crossings",
    ],
    "Observability": [
        "OpenTelemetry traces",
        "OTel logs",
        "OTel metrics",
        "application logs",
        "audit logs",
        "span/resource attributes",
    ],
    "Control 9 (KPI)": [
        "digital twin / KPI exports",
        "metric name",
        "value",
        "unit",
        "timestamp",
        "scope",
        "window/cadence",
    ],
    "Control 16 (usage)": [
        "model gateway usage",
        "input/output tokens",
        "attempt/retry",
        "agent",
        "provider/model",
        "execution state",
    ],
    "Scenario/context": [
        "fault/scenario selection",
        "scenario run lifecycle records (start/stop/inject/complete)",
        "remediation/retest lineage",
        "topology",
        "configuration",
        "state snapshots",
        "policy/config exports",
    ],
}

FILE_FORMAT_GUIDANCE: dict[str, Any] = {
    "supported": [
        "JSON",
        "JSONL/NDJSON",
        "CSV",
        "YAML/YML",
        "LOG/TXT (kv)",
        "OTLP trace JSON/JSONL",
        "OTLP logs JSON/JSONL",
        "OTLP metrics JSON/JSONL",
        "ZIP",
        "TAR",
    ],
    "preferred": {
        "OTel traces": "raw OTLP/JSON where supported",
        "OTel logs": "raw OTLP/JSON where supported",
        "OTel metrics": "raw OTLP/JSON where supported",
        "KPI / digital twin": "CSV or JSON/JSONL",
        "model/token usage": "JSON/JSONL/CSV",
        "API responses": "raw JSON",
        "policy/config": "JSON/YAML",
        "unknown formats": "preserve as opaque evidence — never discard",
    },
    "workflow": (
        "Collect one representative sample → profile/map/qualify it in Source "
        "Setup → then ingest the full calibration/pass/breach evidence."
    ),
}

ADAPTER_DECISION_GATE: dict[str, Any] = {
    "title": "Provider adapter decision gate",
    "steps": [
        "capture the real raw payload",
        "try normal JSON/JSONL/CSV/OTLP ingestion",
        "use Source Setup / MappingProfile",
        "only build a bounded adapter if required semantics cannot be represented safely",
    ],
    "possibleFutureAdapters": [
        "Bedrock model usage / TokenUsage",
        "actual AWS gateway/API export",
    ],
    "rule": "No speculative provider hard-coding — adapters are event-triggered only.",
}

# Telemetry ingestion readiness — capability truth, never a live-connection
# claim. Intake capability describes what the desktop can parse today;
# live binding of the organizer's concrete shapes is an onsite Source
# Setup step. No row claims DATA_OBSERVED until real records exist.
TELEMETRY_READINESS: dict[str, Any] = {
    "title": "Telemetry ingestion readiness",
    "columns": ["Source", "Intake capability", "Live binding"],
    "rows": [
        ["OTel traces", "AVAILABLE", "ONSITE VERIFY"],
        ["OTel logs", "AVAILABLE", "ONSITE VERIFY"],
        ["OTel metrics", "AVAILABLE", "ONSITE VERIFY"],
        ["CloudWatch", "STRUCTURED INTAKE AVAILABLE", "ONSITE VERIFY"],
        ["Model gateway", "STRUCTURED INTAKE AVAILABLE", "ONSITE VERIFY"],
        ["ServiceNow/AICT", "FILE/EXPORT EVIDENCE PATH", "ONSITE VERIFY"],
        ["HAIEC Manifest 1.2", "AVAILABLE", "MANUAL IMPORT"],
    ],
    "note": (
        "Supplied telemetry is an input to qualify, not a verdict. "
        "Timestamp proximity never establishes run membership and an OTLP "
        "metric is never automatically the C9 KPI — both require native "
        "relation or an approved deterministic mapping."
    ),
}

SOURCE_INTEL: dict[str, Any] = {
    "intro": "For each source ask: what can it probably establish, which controls may use it, what is mapped/approved, what remains unknown, and does it need an adapter?",
    "examples": [
        {
            "source": "Model gateway usage",
            "usefulFor": "C16 — model calls, tokens, retries",
            "notEnoughFor": "C7 action completeness",
        },
        {
            "source": "Digital-twin KPI file",
            "usefulFor": "C9 — KPI values/windows",
            "notEnoughFor": "authorization; C7 expected-event completeness",
        },
        {
            "source": "OTel trace",
            "usefulFor": "correlation, timing, service path",
            "notEnoughFor": "run membership — timestamp proximity is not run membership",
        },
    ],
}

# --------------------------------------------------------------------------
# Calibration / freeze / run roles
# --------------------------------------------------------------------------

CALIBRATION_GUIDANCE: dict[str, Any] = {
    "headline": "CALIBRATION is not an ASSESSED run.",
    "uses": {
        "AIA-LOG-001": [
            "normal event pattern",
            "candidate expected-event list",
            "timing distribution",
        ],
        "AIA-ARC-006": [
            "metric behavior",
            "baseline candidate",
            "window quality",
        ],
        "ACN-COST-001": [
            "token distribution",
            "retry behavior",
            "participating agents",
        ],
    },
    "rule": "Calibration statistics inform policy. They never automatically become policy.",
}

FREEZE_GATE: dict[str, Any] = {
    "title": "HAIEC freeze gate — check before any assessed run",
    "copy": (
        "Freeze the governing policy in HAIEC before any assessed run — the "
        "record that must exist is the Frozen Event Governing Instance (the "
        "event-specific policy carrying this event's actual thresholds/"
        "baseline/budget), not the reusable control definition. The "
        "organizer's example values are illustrative, not defaults."
    ),
    "checklist": [
        "Control chosen",
        "Metric defined",
        "Measurement basis defined",
        "Candidate limit/cap selected by team",
        "Exception tolerance defined",
        "Owner identified",
        "Version/date planned",
        "C7 manifest / C9 baseline / C16 accounting basis identified",
        "HAIEC governing policy frozen",
    ],
    "externalItem": (
        "The last item is external: UNKNOWN unless an explicit HAIEC "
        "reference/status is supplied — LogSense never infers it."
    ),
}

RUN_ROLE_COPY = (
    "RUN ROLE is not a verdict. ASSESSED_PASS means the team's intended "
    "demonstration run expected to satisfy the frozen rule — not that it "
    "passed. ASSESSED_BREACH means an intentionally degraded demonstration "
    "run. HAIEC still computes the result."
)

SAME_POLICY_COPY = (
    "The PASS demonstration and the BREACH demonstration must run under the "
    "same frozen governing policy/version. Never change the threshold, "
    "baseline, cap, or exception tolerance between the two runs to "
    "manufacture the expected result."
)

JUDGE_FLOW = (
    "Target judge experience: 'Show me Control 16 for run FM-B' or 'Was "
    "Control 9 satisfied for FM-B / W10?' → HAIEC resolves control + "
    "run/window against the Frozen Event Governing Instance and returns the "
    "deterministic result; LogSense provides the measurement and evidence "
    "drilldown behind that answer. The judge path: Reusable Control → "
    "Frozen Event Governing Instance → Run → Measurement → HAIEC Control "
    "Test → Result → Evidence → Gap / Retest."
)

THRESHOLD_DOC_GUIDANCE: dict[str, Any] = {
    "title": "What the HAIEC Threshold Document must contain",
    "perControl": [
        "control ID/name",
        "control version",
        "metric",
        "limit/cap",
        "comparator/operator",
        "exception tolerance",
        "measurement basis",
        "scope",
        "owner",
        "effective/frozen timestamp",
        "threshold / baseline / budget version",
        "rationale/basis",
        "policy digest",
    ],
    "controlSpecific": {
        "AIA-LOG-001": [
            "coverage target",
            "gap limit",
            "LT/LTE comparator",
            "allowed violating-gap rate",
        ],
        "AIA-ARC-006": [
            "actual KPI",
            "unit",
            "direction",
            "window/aggregation",
            "baseline version/digest",
            "drift limit",
            "violating-window allowance",
            "coverage requirement",
        ],
        "ACN-COST-001": [
            "ActualRunTokens = Σ(inputTokens + outputTokens)",
            "all participating agents",
            "all real provider executions/retries",
            "cap",
            "allowed over-cap rule",
        ],
    },
    "note": "Organizer worked numbers are illustrative, not defaults.",
}

ADVERSARIAL_GUIDE: dict[str, Any] = {
    "intro": "Record for each attack: Attack · Expected defense · Actual result · Evidence · What broke · Supported cause/limitation · Change · Retest · Outcome.",
    "perControl": {
        "AIA-LOG-001": [
            "drop a required event",
            "duplicate an event",
            "out-of-order event",
            "remove a qualified timestamp",
            "corrupt a run ID",
        ],
        "AIA-ARC-006": [
            "missing KPI window",
            "wrong unit",
            "profile version change",
            "scope mismatch",
            "zero baseline",
        ],
        "ACN-COST-001": [
            "retry storm",
            "duplicate usage telemetry",
            "missing token field",
            "replayed provider request ID",
            "concurrent agents near cap",
            "bypass primary enforcement point",
        ],
    },
    "rule": "Help/runbook only — do not mutate real evidence to create attacks.",
}

JUDGE_REHEARSAL: dict[str, Any] = {
    "target": "two-minute judge flow",
    "segments": [
        ("0–15s", "identify control + run/window"),
        ("15–35s", "show the frozen governing version in HAIEC"),
        ("35–60s", "show the deterministic result/calculation"),
        ("60–90s", "open LogSense evidence"),
        ("90–110s", "show gaps/nonclaims"),
        ("110–120s", "show threshold/architecture/export"),
    ],
    "acceptance": [
        "no DB query",
        "no code edit",
        "no grep",
        "no raw JSON as the first view",
        "another teammate can operate it",
    ],
}

SIX_ARTIFACTS: list[dict[str, Any]] = [
    {
        "key": "evidenceFile",
        "name": "Evidence File",
        "owner": "LogSense",
        "help": "The portable judge evidence pack produced by the Export step.",
    },
    {
        "key": "thresholdDocument",
        "name": "Threshold Document",
        "owner": "HAIEC",
        "help": "LogSense provides guidance + an external readiness/ref field; the document itself is HAIEC-owned.",
    },
    {
        "key": "controlTestTool",
        "name": "Control Test Tool",
        "owner": "HAIEC",
        "help": "LogSense provides the handoff/evidence; the evaluator is HAIEC's.",
    },
    {
        "key": "twoNamedRuns",
        "name": "Two Named Runs",
        "owner": "LogSense run register + HAIEC result history",
        "help": "A named intended-PASS run and a named intended-breach run under the same frozen policy.",
    },
    {
        "key": "architecture",
        "name": "One-Page Architecture",
        "owner": "team artifact",
        "help": "LogSense provides a template/helper; the team owns the final page.",
    },
    {
        "key": "gapList",
        "name": "Gap List",
        "owner": "LogSense gap register + HAIEC governance gaps if supplied",
        "help": "Exportable deterministic gap register; HAIEC-side governance gaps only when externally supplied.",
    },
]

COMMON_MISTAKES: list[str] = [
    "Treating a LogSense measurement as a HAIEC verdict.",
    "Treating a run role (ASSESSED_PASS) as a pass result.",
    "Treating missing KPI/event/usage evidence as zero.",
    "Treating timestamp proximity as run membership.",
    "Treating duplicate telemetry as a retry (or a retry as a duplicate).",
    "Computing drift across incompatible baseline/live semantics.",
    "Changing policy between the pass and breach demonstrations.",
    "Claiming 'competition complete' when only LogSense export finished.",
    "Spending bonus time while a core control is non-judgeable.",
]

# --------------------------------------------------------------------------
# AI competition-guide content (advisory — never forensic truth)
# --------------------------------------------------------------------------

AI_GUIDE_BANNER = "COMPETITION GUIDANCE — NOT FORENSIC EVIDENCE"

AI_MUST_NOT: list[str] = [
    "approve mappings",
    "infer run membership as truth",
    "choose metric direction automatically",
    "freeze/select the governing baseline",
    "choose threshold/cap",
    "claim HAIEC policy is frozen",
    "invent missing evidence",
    "turn missing evidence into zero",
    "create SATISFIED / NOT_SATISFIED",
    "change deterministic measurements",
    "rewrite a run role into a verdict",
]

# Deterministic answers for the provider-off fallback AND the bounded context
# the AI guide mode uses. Keys are stable action identifiers.
QUICK_ACTIONS: dict[str, dict[str, Any]] = {
    "guide_from_here": {
        "label": "Guide me from here",
        "topic": "workflow",
    },
    "what_missing": {
        "label": "What am I missing?",
        "topic": "gaps",
    },
    "collect_what": {
        "label": "What evidence should I collect?",
        "topic": "evidence_hunting",
    },
    "explain_blocker": {
        "label": "Explain this blocker",
        "topic": "blockers",
    },
    "most_ready": {
        "label": "Which control is most ready?",
        "topic": "feasibility",
    },
    "prepare_handoff": {
        "label": "Prepare HAIEC handoff",
        "topic": "handoff",
    },
    "prepare_judge": {
        "label": "Prepare me for the judge",
        "topic": "rehearsal",
    },
    "six_artifacts": {
        "label": "Explain the six artifacts",
        "topic": "artifacts",
    },
    "bonus_next": {
        "label": "What bonus work is worth doing?",
        "topic": "bonus",
    },
}


def capability_truth() -> dict[str, Any]:
    """Control capability truth for UI/AI — single source for the
    LogSense/HAIEC/Event-Assessed column values."""
    return deepcopy(CAPABILITY_TRUTH)


def ai_guidance_context() -> dict[str, Any]:
    """Bounded competition-guidance context for the AI guide mode.

    Advisory content only — the manifest marks it non-forensic, and the tool
    result stamps COMPETITION_GUIDANCE_NOT_FORENSIC_EVIDENCE. Indexed by
    topic so the ``get_event_guidance`` tool can return one bounded section.
    """
    return {
        "schemaVersion": "ai-competition-guidance/0.1",
        "banner": AI_GUIDE_BANNER,
        "mustNot": list(AI_MUST_NOT),
        "topics": {
            "workflow": {
                "summary": (
                    "UNDERSTAND → DISCOVER → INGEST → MAP → RECONSTRUCT → "
                    "CHOOSE CONTROL → CALIBRATE → FREEZE IN HAIEC → CAPTURE "
                    "ASSESSED RUNS → MEASURE → HAND OFF → INVESTIGATE/RETEST → "
                    "PACKAGE → REHEARSE."
                ),
                "sixSteps": deepcopy(ORGANIZER_SIX_STEPS),
            },
            "gaps": {
                "summary": (
                    "Gaps stay visible: one honest failure beats a fake "
                    "all-green. Check the Gap Register and frontiers."
                ),
            },
            "evidence_hunting": deepcopy(EVIDENCE_HUNTING),
            "blockers": {
                "summary": (
                    "Resolve blockers deterministically: unmapped sources via "
                    "Source Setup; missing runs via Runs; C9 via profile + "
                    "baseline + compatibility preflight; C16 via qualified "
                    "token fields. Missing evidence is never zero."
                ),
            },
            "feasibility": {
                "summary": (
                    "Control feasibility is computed deterministically — see "
                    "get_event_readiness for the live per-control state."
                ),
            },
            "handoff": {
                "summary": (
                    "Hand the Competition Evidence Bundle + measurement refs "
                    "to HAIEC. HAIEC applies the Frozen Event Governing "
                    "Instance and returns the Control Test result. All three "
                    "HAIEC Control Tests are technically available; event "
                    "assessed: NOT YET."
                ),
                "footnote": HAIEC_EVENT_FOOTNOTE,
            },
            "rehearsal": deepcopy(JUDGE_REHEARSAL),
            "artifacts": {"sixArtifacts": deepcopy(SIX_ARTIFACTS)},
            "bonus": deepcopy(JUDGING_AXES["axis3"]),
            "calibration": deepcopy(CALIBRATION_GUIDANCE),
            "freeze_gate": deepcopy(FREEZE_GATE),
            "threshold_document": deepcopy(THRESHOLD_DOC_GUIDANCE),
            "adversarial": deepcopy(ADVERSARIAL_GUIDE),
            "concepts": deepcopy(CONCEPT_VOCABULARY),
            "clock_integrity": deepcopy(FIRST_HOUR_ARTIFACTS["clockIntegrity"]),
            "operator_fallback": {"summary": OPERATOR_FALLBACK},
            "skeptical_stranger": deepcopy(SKEPTICAL_STRANGER_CHECK),
            "common_mistakes": list(COMMON_MISTAKES),
        },
    }


def event_guide() -> dict[str, Any]:
    """The full structured guide, consumed by UI expanders and the AI context."""
    return {
        "schemaVersion": GUIDANCE_SCHEMA,
        "capabilityTruth": deepcopy(CAPABILITY_TRUTH),
        "conceptVocabulary": deepcopy(CONCEPT_VOCABULARY),
        "mission": deepcopy(EVENT_MISSION),
        "labShape": deepcopy(LAB_SHAPE),
        "threeLayers": deepcopy(THREE_LAYERS),
        "organizerArchitecture": deepcopy(ORGANIZER_ARCHITECTURE),
        "judgingAxes": deepcopy(JUDGING_AXES),
        "organizerSixSteps": deepcopy(ORGANIZER_SIX_STEPS),
        "firstHourArtifacts": deepcopy(FIRST_HOUR_ARTIFACTS),
        "firstHourSequence": deepcopy(FIRST_HOUR_SEQUENCE),
        "operatorFallback": OPERATOR_FALLBACK,
        "skepticalStrangerCheck": deepcopy(SKEPTICAL_STRANGER_CHECK),
        "evidenceHunting": deepcopy(EVIDENCE_HUNTING),
        "fileFormats": deepcopy(FILE_FORMAT_GUIDANCE),
        "adapterGate": deepcopy(ADAPTER_DECISION_GATE),
        "telemetryReadiness": deepcopy(TELEMETRY_READINESS),
        "sourceIntel": deepcopy(SOURCE_INTEL),
        "calibration": deepcopy(CALIBRATION_GUIDANCE),
        "freezeGate": deepcopy(FREEZE_GATE),
        "runRoleCopy": RUN_ROLE_COPY,
        "samePolicyCopy": SAME_POLICY_COPY,
        "judgeFlow": JUDGE_FLOW,
        "thresholdDocument": deepcopy(THRESHOLD_DOC_GUIDANCE),
        "adversarial": deepcopy(ADVERSARIAL_GUIDE),
        "judgeRehearsal": deepcopy(JUDGE_REHEARSAL),
        "sixArtifacts": deepcopy(SIX_ARTIFACTS),
        "commonMistakes": list(COMMON_MISTAKES),
        "aiGuideBanner": AI_GUIDE_BANNER,
        "aiMustNot": list(AI_MUST_NOT),
        "quickActions": deepcopy(QUICK_ACTIONS),
    }
