"""Human-readable evidence renderers + the Judgment-Day evidence pack.

Produces standalone HTML that opens on a machine where LogSense is not
installed. Machine JSON stays canonical; HTML is a faithful display
projection with display-only rounding.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any

PACK_NAME = "TMF-JUDGE-EVIDENCE-PACK.zip"
PACK_SCHEMA = "tmf-judge-evidence-pack/0.1"

_STYLE = """
body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;margin:2rem;color:#1a1a1a;max-width:1100px}
h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:1.6rem}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:.5rem 0}
th,td{border:1px solid #ccc;padding:.35rem .5rem;text-align:left;vertical-align:top}
th{background:#f0f2f5}
.state-MEASURED,.state-READY{background:#e7f6e7}
.state-PARTIAL,.state-READY_WITH_LIMITATIONS,.state-UNKNOWN,.state-NOT_YET{background:#fff4d6}
.state-NOT_MEASURED,.state-NOT_READY,.state-INCOMPATIBLE{background:#fbe3e3}
.small{font-size:.8rem;color:#555}
code{background:#f0f2f5;padding:.05rem .3rem;border-radius:3px}
ul.tight{margin:.2rem 0;padding-left:1.2rem}
"""


def _esc(value: Any) -> str:
    return html.escape("—" if value is None else str(value))


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}%"  # display rounding only
    except (TypeError, ValueError):
        return str(value)


def _fmt_num(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _limits(items: Sequence[Any]) -> str:
    if not items:
        return "<p class='small'>None recorded.</p>"
    return "<ul class='tight'>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>"


# --------------------------------------------------------------------------
# Per-control human-readable evidence
# --------------------------------------------------------------------------


def render_control7_html(measurement: Mapping[str, Any]) -> str:
    """Standalone judge-viewable Control 7 evidence page."""
    cov = measurement.get("coverage") or {}
    timing = measurement.get("timing") or {}
    observed = measurement.get("observed") or {}
    matched_rows = [
        [
            _esc(m.get("expectedEventId")),
            _esc(m.get("observedEventRef")),
            _esc(m.get("observedEventTime")),
        ]
        for m in measurement.get("matched") or ()
    ]
    missing_rows = [[_esc(e)] for e in measurement.get("missingEvents") or ()]
    unexpected_rows = [[_esc(e.get("observedEventRef"))] for e in measurement.get("unexpectedEvents") or ()]
    dup_rows = [
        [_esc(d.get("expectedEventId")), _esc(d.get("observedEventRef"))]
        for d in measurement.get("duplicates") or ()
    ]
    gap_rows = [
        [
            _esc(
                f"{g.get('previousExpectedEventId') or g.get('previousEventRef') or '?'} → "
                f"{g.get('nextExpectedEventId') or g.get('nextEventRef') or '?'}"
            ),
            _fmt_num(g.get("gapMs") if g.get("gapMs") is not None else g.get("observedGapMs")),
            _fmt_num(g.get("gapLimitMs") or timing.get("declaredGapLimitMs")),
            _esc(timing.get("effectiveGapComparator")),
            _esc(g.get("gapState"))
            + (" (violates)" if g.get("violatesDeclaredLimit") else ""),
        ]
        for g in measurement.get("timingGaps") or ()
    ]
    body = f"""
<p><b>Control:</b> AIA-LOG-001 — Event Recording &nbsp; <b>Run:</b> {_esc(measurement.get('runId'))}
&nbsp; <b>State:</b> <span class='state-{_esc(measurement.get('measurementState'))}'>{_esc(measurement.get('measurementState'))}</span></p>
<p class='small'>Manifest {_esc(measurement.get('expectedManifestRef'))} · snapshot {_esc(measurement.get('activeSnapshotRef'))}
· measurement digest <code>{_esc(measurement.get('measurementDigest'))}</code></p>
<h2>Coverage</h2>
{_table(["Expected", "Required", "Matched required", "Overall matched", "Coverage"],
        [[_esc((measurement.get('expected') or {}).get('count')),
          _esc(cov.get('expectedRequired')), _esc(cov.get('matchedRequired')),
          _esc(cov.get('overallMatched')), _fmt_pct(cov.get('percent'))]])}
<p class='small'>Observed {observed.get('count', '—')} · matched {observed.get('matchedCount', '—')}
· unexpected {observed.get('unexpectedCount', '—')} · duplicates {observed.get('duplicateCount', '—')}</p>
<h2>Timing gaps</h2>
<p class='small'>Comparator {_esc(timing.get('effectiveGapComparator'))} (source {_esc(timing.get('gapComparatorSource'))}) ·
eligible {_esc(timing.get('eligibleGaps'))} · measured {_esc(timing.get('measuredGaps'))} ·
violating {_esc(timing.get('violatingGaps'))} · violation rate {_fmt_pct(timing.get('violationPercent'))}</p>
{_table(["Gap", "Observed ms", "Declared limit ms", "Comparator", "State"], gap_rows) if gap_rows else "<p class='small'>No timing gaps.</p>"}
<h2>Matched events</h2>
{_table(["Expected event", "Observed ref", "Observed at"], matched_rows) if matched_rows else "<p class='small'>None.</p>"}
<h2>Missing / unexpected / duplicate</h2>
{_table(["Missing expected event"], missing_rows) if missing_rows else "<p class='small'>No missing expected events.</p>"}
{_table(["Unexpected observed ref"], unexpected_rows) if unexpected_rows else ""}
{_table(["Duplicate of", "Observed ref"], dup_rows) if dup_rows else ""}
{("<p class='small'>Run-lifecycle markers bound to this run (outside the manifest's behavioral domain): "
  + _esc(", ".join(e.get("observedEventRef") for e in measurement.get("runLifecycleEvents") or ()))
  + "</p>") if measurement.get("runLifecycleEvents") else ""}
<h2>Limitations</h2>{_limits(measurement.get('limitations') or ())}
<p class='small'>Measurement only — verdict: <code>null</code>, verdict owner: HAIEC.</p>
"""
    return _page("Control 7 — Event Recording (AIA-LOG-001)", body)


def render_control9_html(measurement: Mapping[str, Any]) -> str:
    """Standalone judge-viewable Control 9 evidence page."""
    compat = measurement.get("compat") or measurement.get("compatibility") or {}
    dim_rows = [
        [_esc(d.get("dimension")), _esc(d.get("baseline")), _esc(d.get("live")), _esc(d.get("state"))]
        for d in compat.get("dimensions") or ()
    ]
    window_rows = [
        [
            _esc(w.get("windowKey") or w.get("windowId")),
            _fmt_num(w.get("baselineValue")),
            _fmt_num(w.get("liveValue")),
            _fmt_num(w.get("absoluteDelta")),
            _fmt_pct(w.get("relativeDegradationPercent")),
            f"<span class='state-{_esc(w.get('comparisonState'))}'>{_esc(w.get('comparisonState'))}</span>",
            _esc(", ".join((w.get("liveEvidenceRefs") or ())[:2])),
        ]
        for w in measurement.get("windows") or ()
    ]
    body = f"""
<p><b>Control:</b> AIA-ARC-006 — Drift &amp; Performance &nbsp; <b>Run:</b> {_esc(measurement.get('runId'))}
&nbsp; <b>State:</b> <span class='state-{_esc(measurement.get('measurementState'))}'>{_esc(measurement.get('measurementState'))}</span></p>
<p class='small'>Profile {_esc(measurement.get('metricProfileRef'))} · baseline {_esc(measurement.get('baselineRef'))}
· snapshot {_esc(measurement.get('activeSnapshotRef'))} · digest <code>{_esc(measurement.get('measurementDigest'))}</code></p>
<h2>Coverage</h2>
{_table(["Expected windows", "Observed qualified", "Comparable", "Coverage"],
        [[_esc(measurement.get('expectedWindows')), _esc(measurement.get('observedQualifiedWindows')),
          _esc(measurement.get('comparableMeasuredWindows')), _fmt_pct(measurement.get('coveragePercent'))]])}
<h2>Compatibility</h2>
<p class='small'>Overall: {_esc(compat.get('overallState'))}</p>
{_table(["Dimension", "Baseline", "Live", "State"], dim_rows) if dim_rows else "<p class='small'>Not evaluated.</p>"}
<h2>Windows</h2>
{_table(["Window", "Baseline", "Live", "Abs. delta", "Rel. degradation", "State", "Evidence"], window_rows)}
<h2>Limitations</h2>{_limits(measurement.get('limitations') or ())}
<p class='small'>Measurement only — verdict: <code>null</code>, verdict owner: HAIEC.
Display values rounded; canonical JSON carries exact machine values.</p>
"""
    return _page("Control 9 — Drift & Performance (AIA-ARC-006)", body)


def render_control16_html(measurement: Mapping[str, Any]) -> str:
    """Standalone judge-viewable Control 16 evidence page."""
    usage_rows = [
        [
            _esc(r.get("agentId")),
            _esc(r.get("modelCallId")),
            _esc(r.get("providerRequestId")),
            _esc(r.get("attemptNumber")),
            _esc(r.get("inputTokens")),
            _esc(r.get("outputTokens")),
            _esc(r.get("scoredTokens") if r.get("scoredTokens") is not None else r.get("totalTokens")),
            _esc(r.get("executionState")),
            _esc(r.get("usageQualification") or r.get("qualification")),
            _esc(r.get("sourceEventRef")),
        ]
        for r in measurement.get("usageRecords") or ()
    ]
    agent_rows = [
        [_esc(a.get("agentId")), _esc(a.get("executedCalls")), _esc(a.get("totalTokens"))]
        for a in measurement.get("perAgentBreakdown") or ()
    ]
    actual = measurement.get("actualRunTokens")
    actual_line = (
        f"<b>ActualRunTokens:</b> {actual}"
        if actual is not None
        else "<b>ActualRunTokens: Not fully established</b> "
             f"(known qualified subtotal: {_esc(measurement.get('knownQualifiedTokens'))})"
    )
    body = f"""
<p><b>Control:</b> ACN-COST-001 — Agent Spend Cap &nbsp; <b>Run:</b> {_esc(measurement.get('runId'))}
&nbsp; <b>State:</b> <span class='state-{_esc(measurement.get('measurementState'))}'>{_esc(measurement.get('measurementState'))}</span></p>
<p class='small'>Snapshot {_esc(measurement.get('activeSnapshotRef'))} ·
digest <code>{_esc(measurement.get('measurementDigest'))}</code></p>
<p>{actual_line}<br>
<span class='small'>Input {_esc(measurement.get('totalInputTokens'))} + output {_esc(measurement.get('totalOutputTokens'))}
· provider-executed calls {_esc(measurement.get('providerExecutedCalls'))} ·
retries {_esc(measurement.get('retryExecutions'))} · duplicates suppressed {_esc(measurement.get('duplicateTelemetryRecordsSuppressed'))}
· missing usage {_esc(measurement.get('missingUsageCalls'))}</span></p>
<h2>Per-agent breakdown</h2>
{_table(["Agent", "Executed calls", "Tokens"], agent_rows) if agent_rows else "<p class='small'>None.</p>"}
<h2>Usage records</h2>
{_table(["Agent", "Model call", "Provider request", "Attempt", "Input", "Output", "Scored", "Execution", "Qualification", "Evidence"], usage_rows)}
<h2>Limitations</h2>{_limits(measurement.get('limitations') or ())}
<p class='small'>Measurement only — verdict: <code>null</code>, verdict owner: HAIEC.
Missing usage is not zero tokens; genuine retries count again.</p>
"""
    return _page("Control 16 — Agent Spend Cap (ACN-COST-001)", body)


# --------------------------------------------------------------------------
# Register + index pages
# --------------------------------------------------------------------------


def render_run_activity_html(activity: Mapping[str, Any]) -> str:
    """Standalone judge-viewable run-activity provenance page."""
    state = str(activity.get("startState") or "NOT_ESTABLISHED")
    state_note = {
        "ESTABLISHED": (
            "Run start established from explicit qualified evidence — ready "
            "for HAIEC pre-run temporal-policy proof."
        ),
        "NOT_ESTABLISHED": (
            "No explicit qualified run-start fact exists. RUN_DECLARATION_TIME "
            "!= RUN_START and EARLIEST_OBSERVED_ACTIVITY != RUN_START — "
            "LogSense fails closed rather than inferring a start."
        ),
        "CONFLICTING": (
            "Qualified sources assert different run-start times. LogSense "
            "never selects a winner; reconcile the source facts."
        ),
    }.get(state, "Run-start evidence unavailable.")
    body = f"""
<p><b>Run:</b> {_esc(activity.get('runId'))} &nbsp;
<b>Run start:</b> <span class='state-{'READY' if state == 'ESTABLISHED' else 'NOT_READY'}'>{_esc(state)}</span></p>
<p>{html.escape(state_note)}</p>
{_table(["Field", "Value"], [
    ["runStartedAt", _esc(activity.get("runStartedAt"))],
    ["runCompletedAt", _esc(activity.get("runCompletedAt"))],
    ["earliestObservedActivityAt", _esc(activity.get("earliestObservedActivityAt"))],
    ["latestObservedActivityAt", _esc(activity.get("latestObservedActivityAt"))],
    ["startBasis", _esc(", ".join(activity.get("startBasis") or ()))],
    ["startEvidenceRefs", _esc(", ".join(activity.get("startEvidenceRefs") or ()))],
    ["observedActivityEvidenceRefs", _esc(", ".join(activity.get("observedActivityEvidenceRefs") or ()))],
    ["excludedStartCandidateRefs", _esc(", ".join(activity.get("excludedStartCandidateRefs") or ()))],
    ["sourceRefs", _esc(", ".join(activity.get("sourceRefs") or ()))],
])}
<p class='small'><b>Earliest observed activity is not automatically the assessed run
start.</b> Only evidence carrying explicit run-start semantics establishes
<code>runStartedAt</code>; excluded start candidates are listed, never trusted.</p>
<h2>Limitations</h2>{_limits(activity.get('limitations') or ())}
<p class='small'>Provenance only — LogSense describes run activity; HAIEC decides
whether the frozen policy preceded the assessed run.</p>
"""
    return _page(f"Run Activity — {activity.get('runId') or 'run'}", body)


def render_run_register_html(register: Mapping[str, Any]) -> str:
    rows = [
        [
            _esc(r.get("runId")),
            _esc(r.get("runRole")),
            _esc(r.get("scenarioLabel")),
            _esc(r.get("resolutionState")),
            _esc(r.get("runStartState")),
            _esc(r.get("runStartedAt")),
            _esc(", ".join(r.get("controlsMeasured") or ())),
            _esc(
                "; ".join(
                    f"{c}={s}" for c, s in (r.get("measurementStates") or {}).items()
                )
            ),
            _esc(r.get("retestOfRunId")),
        ]
        for r in register.get("runs") or ()
    ]
    body = (
        _table(
            ["Run", "Role", "Scenario", "Resolution", "Run start", "Started at",
             "Controls measured", "States", "Retest of"],
            rows,
        )
        + "<p class='small'>Run start reflects explicit qualified run-start "
          "evidence only — earliest observed activity never implies RUN_START.</p>"
        + f"<p class='small'>{_esc(register.get('note'))}</p>"
    )
    return _page("Run Register", body)


def render_gap_register_html(register: Mapping[str, Any]) -> str:
    rows = [
        [
            _esc(g.get("gapId")),
            _esc(g.get("category")),
            _esc(g.get("control")),
            _esc(g.get("run")),
            _esc(g.get("gap")),
            _esc(g.get("whyItMatters")),
            _esc(g.get("consequence")),
            _esc(g.get("whatRemainsSupportable")),
            _esc(g.get("nextAction")),
        ]
        for g in register.get("gaps") or ()
    ]
    body = (
        _table(
            [
                "Gap",
                "Category",
                "Control",
                "Run",
                "What is blocking",
                "Why it matters",
                "Consequence",
                "Still supportable",
                "Next action",
            ],
            rows,
        )
        + f"<p class='small'>{_esc(register.get('note'))}</p>"
    )
    return _page("Gap Register", body)


def render_architecture_html(labels: Mapping[str, Any] | None = None) -> str:
    """One-page architecture template — labels editable by the team."""
    labels = dict(labels or {})
    get = lambda k, default: html.escape(str(labels.get(k) or default))  # noqa: E731
    body = f"""
<h2>Supplied runtime</h2>
<pre>{get('customerZone', 'Customer Zone: chat agent + trouble ticket')}
   → {get('gatewayA', 'Gateway A')}
{get('itZone', 'IT Zone: triage agent + account records (AWS)')}
   → {get('gatewayB', 'Gateway B')}
{get('networkZone', 'Network Zone: investigation agent + inventory + digital twin (AWS/NVIDIA)')}

{get('modelGateway', 'Shared Model Gateway — used by model calls across zones')}
{get('telemetry', 'Telemetry: OTel collector/storage · digital twin · scenario switch')}</pre>
<h2>Assurance layer</h2>
<pre>LogSense — forensic evidence, reconstruction, C7/C9/C16 measurement
HAIEC   — control register, evaluator, evidence/result binding, Control Test</pre>
<p class='small'>Rename labels to the actual event names. Guidance only.</p>
"""
    return _page("One-Page Architecture (template)", body)


def render_start_here_html(
    *,
    case_id: str,
    register: Mapping[str, Any],
    pack_manifest: Mapping[str, Any],
) -> str:
    measured = sorted(
        {
            code
            for r in register.get("runs") or ()
            for code in (r.get("controlsMeasured") or ())
        }
    )
    body = f"""
<p><b>Package:</b> TMF Judgment-Day Evidence Pack &nbsp; <b>Case:</b> {_esc(case_id)}
&nbsp; <b>Created:</b> {_esc(pack_manifest.get('createdAt'))}</p>
<h2>What this package is</h2>
<p>Deterministic LogSense evidence for the named competition runs —
reconstruction, Control 7/9/16 measurements, registers and gaps. It opens in
any browser; LogSense is not required.</p>
<h2>Contents</h2>
<ul class='tight'>
<li><code>runs/run-register.html|json</code> — every declared run, role, resolution and measured controls.</li>
<li><code>evidence/&lt;runId&gt;/</code> — run resolution, qualified run-activity provenance
(<code>run-activity.json</code>/<code>.html</code>), source manifest, snapshot ref, and per-control
<code>control7|9|16.json</code> (canonical) + <code>.html</code> (readable) + <code>limitations.json</code>.</li>
<li><code>gaps/gap-register.html|json</code> — the exportable gap register.</li>
<li><code>architecture/README.html</code> — the one-page architecture template.</li>
<li><code>external/haiec-references.json</code> — HAIEC result/threshold references, only when actually supplied.</li>
</ul>
<h2>How to read it</h2>
<ul class='tight'>
<li>The judge path: <b>Reusable Control → Frozen Event Governing Instance →
Run → Measurement → HAIEC Control Test → Result → Evidence → Gap / Retest</b>.
This pack supplies the Run, Measurement, Evidence and Gap links; the
governing instance and result are HAIEC-side.</li>
<li>Open the <code>.html</code> files first — they are readable projections.
<code>.json</code> twins are canonical and digest-bound.</li>
<li>Each run folder's <code>limitations.json</code> lists what cannot be claimed
and a per-file guide (<code>fileGuide</code>).</li>
<li><code>package-manifest.json</code> carries a SHA-256 for every file —
integrity is verifiable offline.</li>
<li>Run roles are workflow labels, not verdicts. No SATISFIED/NOT_SATISFIED
appears unless an external HAIEC reference was supplied.</li>
<li>Run start is proven only by explicit qualified run-start evidence —
never by the earliest observed timestamp. Check
<code>evidence/&lt;runId&gt;/run-activity.html</code> for each run's
ESTABLISHED / NOT ESTABLISHED / CONFLICTING state.</li>
</ul>
<h2>Runs in this pack</h2>
{_table(["Run", "Role", "Scenario", "Run start", "Controls measured"],
        [[_esc(r.get('runId')), _esc(r.get('runRole')), _esc(r.get('scenarioLabel')),
          _esc(r.get('runStartState')),
          _esc(', '.join(r.get('controlsMeasured') or ()))] for r in register.get('runs') or ()])}
<p class='small'>Controls with measurements: {', '.join(measured) if measured else 'none'}.
This package contains no HAIEC verdict — SATISFIED/NOT_SATISFIED results appear
only if an external HAIEC reference/result was supplied (see <code>external/</code>).</p>
"""
    return _page("TMF Judgment-Day Evidence Pack — Start Here", body)


# --------------------------------------------------------------------------
# Pack assembly
# --------------------------------------------------------------------------


def build_judge_pack(
    *,
    case_id: str,
    created_at: str,
    source_version: str,
    source_git_sha: str | None,
    register: Mapping[str, Any],
    gap_reg: Mapping[str, Any],
    per_run: Mapping[str, Mapping[str, Any]],
    external_refs: Mapping[str, Any] | None,
    architecture_labels: Mapping[str, Any] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Assemble the TMF-JUDGE-EVIDENCE-PACK zip.

    ``per_run`` maps runId → {"resolution", "sourceManifest", "snapshot",
    "measurements": {controlCode: measurement}, "limitations": [...]}.
    Returns ``(zip_bytes, package_manifest)``.
    """
    manifest: dict[str, Any] = {
        "schemaVersion": PACK_SCHEMA,
        "packageVersion": "0.1",
        "createdAt": created_at,
        "sourceLogSenseVersion": source_version,
        "sourceGitSha": source_git_sha,
        "caseId": case_id,
        "runs": [str(r.get("runId")) for r in register.get("runs") or ()],
        "files": [],
        "measurementRefs": [],
        "externalHaiecRefs": None,
        "note": (
            "Deterministic LogSense outputs + readable projections. No HAIEC "
            "verdict is included unless an external reference was supplied."
        ),
    }
    files: dict[str, bytes] = {}

    def put(name: str, content: str | bytes, *, track: bool = True) -> None:
        data = content.encode("utf-8") if isinstance(content, str) else content
        files[f"TMF-JUDGE-EVIDENCE-PACK/{name}"] = data
        if track:
            manifest["files"].append(
                {
                    "path": f"TMF-JUDGE-EVIDENCE-PACK/{name}",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            )

    def put_json(name: str, payload: Any) -> None:
        put(name, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    put_json("runs/run-register.json", register)
    put("runs/run-register.html", render_run_register_html(register))
    put_json("gaps/gap-register.json", gap_reg)
    put("gaps/gap-register.html", render_gap_register_html(gap_reg))
    put("architecture/README.html", render_architecture_html(architecture_labels))

    for run_id, bundle in per_run.items():
        base = f"evidence/{run_id}"
        if bundle.get("resolution"):
            put_json(f"{base}/run-resolution.json", bundle["resolution"])
        if bundle.get("runActivity"):
            put_json(f"{base}/run-activity.json", bundle["runActivity"])
            put(f"{base}/run-activity.html", render_run_activity_html(bundle["runActivity"]))
        if bundle.get("sourceManifest"):
            put_json(f"{base}/source-manifest.json", bundle["sourceManifest"])
        if bundle.get("snapshot"):
            put_json(f"{base}/snapshot.json", bundle["snapshot"])
        renderers = {
            "AIA-LOG-001": ("control7", render_control7_html),
            "AIA-ARC-006": ("control9", render_control9_html),
            "ACN-COST-001": ("control16", render_control16_html),
        }
        file_guide = {
            "limitations.json": (
                "What cannot be claimed for this run, plus this file guide. "
                "Codes are stable machine identifiers."
            ),
        }
        if bundle.get("resolution"):
            file_guide["run-resolution.json"] = (
                "How this run was identified and which evidence belongs to it; "
                "ambiguous, unresolved, foreign and unidentified evidence is "
                "listed rather than silently dropped."
            )
        if bundle.get("sourceManifest"):
            file_guide["source-manifest.json"] = (
                "The evidence artifacts (with sha256 digests) that fed this run."
            )
        if bundle.get("snapshot"):
            file_guide["snapshot.json"] = (
                "The immutable analysis snapshot these measurements were "
                "computed against."
            )
        if bundle.get("runActivity"):
            file_guide["run-activity.json"] = (
                "Qualified run-activity provenance — whether explicit "
                "evidence established the actual assessed run start "
                "(ESTABLISHED/NOT_ESTABLISHED/CONFLICTING). Earliest observed "
                "activity is never the run start."
            )
            file_guide["run-activity.html"] = (
                "Readable projection of run-activity.json — open this first."
            )
        limitations = sorted(
            {
                lim
                for measurement in (bundle.get("measurements") or {}).values()
                if measurement
                for lim in (measurement.get("limitations") or ())
            }
            | set((bundle.get("runActivity") or {}).get("limitations") or ())
        )
        for code, measurement in sorted((bundle.get("measurements") or {}).items()):
            if not measurement:
                continue
            stem, renderer = renderers.get(code, (code.lower(), None))
            put_json(f"{base}/{stem}.json", measurement)
            file_guide[f"{stem}.json"] = (
                f"Canonical {code} measurement — digest-bound; "
                "verdict stays null (HAIEC owns the Control Test)."
            )
            if renderer is not None:
                put(f"{base}/{stem}.html", renderer(measurement))
                file_guide[f"{stem}.html"] = (
                    f"Readable projection of {stem}.json — open this first."
                )
            ref = measurement.get("measurementDigest") or measurement.get("measurementRef")
            if ref:
                manifest["measurementRefs"].append(
                    {"runId": run_id, "control": code, "digest": ref}
                )
        put_json(
            f"{base}/limitations.json",
            {
                "schemaVersion": "judge-pack-run-limitations/0.1",
                "runId": run_id,
                "note": (
                    "Everything LogSense cannot claim for this run. Open the "
                    "controlN.html files first — the JSON twins are canonical, "
                    "digest-bound measurements."
                ),
                "fileGuide": file_guide,
                "limitations": limitations,
            },
        )

    if external_refs:
        manifest["externalHaiecRefs"] = dict(external_refs)
        put_json("external/haiec-references.json", dict(external_refs))

    put("00-START-HERE.html", render_start_here_html(
        case_id=case_id, register=register, pack_manifest=manifest))
    # The manifest lists every other file's digest; it is not hashed into
    # itself.
    put(
        "package-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        track=False,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    return buffer.getvalue(), manifest
