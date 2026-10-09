"""Control 16 / ACN-COST-001 — post-run token & retry reconciliation.

The scored forensic quantity is::

    ActualRunTokens = Σ(inputTokens + outputTokens)

across every unique provider-executed model-call attempt bound to the
confirmed CompetitionRun — all participating agents and every genuine retry.
Duplicate telemetry for one provider execution counts once; a real retry that
reached the provider counts again.

This module is measurement-only. It never decides whether the run satisfied a
token/spend cap — ``verdict`` is always ``None`` and ``verdictOwner`` is
``HAIEC``. Dollar pricing, reservations, live enforcement, and provider
pricing tables are deliberately absent.

Determinism contract:

- usage facts come only from canonical-event ``attributes`` (the preserved
  raw record) — never from AI, similarity, or timestamp proximity;
- run membership is inherited verbatim from ``resolve_competition_run``;
- execution identity uses explicit ids only: ``(provider, providerRequestId)``
  wins, else ``modelCallId`` + ``attemptNumber``. Records that cannot prove
  they are duplicates of one execution are never suppressed — they count and
  the run surfaces ``POSSIBLE_DUPLICATE_IDENTITY_UNRESOLVED``;
- token values must be real non-negative integers. Strings, floats, bools
  and negatives make the usage ``UNQUALIFIED`` — never silently coerced;
- token field semantics are qualified separately from generic event
  mapping: literal ``inputTokens``/``outputTokens`` on an approved-mapped
  artifact qualify via ``DIRECT_CANONICAL_FIELD_NAMES``; raw aliases need an
  explicit approved field mapping or a conditional token accounting
  profile — name resemblance alone never qualifies;
- generic denial/timeout markers do not prove execution stage —
  ``DENIED``/``TIMEOUT`` resolve to ``UNKNOWN`` unless explicit
  pre-execution or dispatch evidence exists;
- provider-specific auxiliary token fields (``cacheReadTokens``,
  ``reasoningTokens``, …) are preserved in ``rawTokenFields`` and are never
  added to the scored total.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from logsense.competition.run import declared_identifier_sets, event_identifiers

CONTROL16_CODE = "ACN-COST-001"
CONTROL16_MEASUREMENT_SCHEMA = "control16-usage-reconciliation/0.1"
USAGE_RECORD_SCHEMA = "model-call-usage-record/0.1"

EXECUTION_STATES = (
    "PROVIDER_EXECUTED",  # evidence establishes the provider/model executed
    "DENIED_BEFORE_EXECUTION",  # denied before provider execution — zero tokens
    "FAILED_BEFORE_EXECUTION",  # failed before provider execution — zero tokens
    "DISPATCHED_PENDING",  # dispatched; completion/usage unresolved — not zero
    "UNKNOWN",  # cannot establish executed vs non-executed
)

USAGE_QUALIFICATIONS = ("QUALIFIED", "PROVISIONAL", "UNKNOWN")
MAPPING_QUALIFICATIONS = ("QUALIFIED", "PROVISIONAL", "UNKNOWN")
MEASUREMENT_STATES = ("MEASURED", "PARTIAL", "NOT_MEASURED")


def _first(attributes: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = attributes.get(key)
        if value not in (None, ""):
            return value
    return None


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


_MODEL_CALL_ID_KEYS = ("modelCallId", "model_call_id", "llmCallId", "llm_call_id")
_PROVIDER_REQUEST_KEYS = (
    "providerRequestId",
    "provider_request_id",
    "providerExecutionId",
    "provider_execution_id",
)
_AGENT_KEYS = ("agentId", "agent_id", "agent")
_MODEL_KEYS = ("modelId", "model_id", "modelName", "model_name", "model")
_PROVIDER_KEYS = ("provider",)
_ATTEMPT_KEYS = ("attemptNumber", "attempt_number", "attempt")
_RETRY_OF_KEYS = ("retryOfModelCallId", "retry_of_model_call_id", "retryOf", "retry_of")
_EXECUTION_STATE_KEYS = ("executionState", "execution_state")
_STATUS_KEYS = ("status", "outcome", "result")
_INPUT_TOKEN_KEYS = ("inputTokens", "input_tokens", "promptTokens", "prompt_tokens")
_OUTPUT_TOKEN_KEYS = ("outputTokens", "output_tokens", "completionTokens", "completion_tokens")
_TOTAL_TOKEN_KEYS = ("totalTokens", "total_tokens")
_STARTED_KEYS = ("startedAt", "started_at", "started")
_COMPLETED_KEYS = ("completedAt", "completed_at", "finishedAt", "finished_at", "completed")
_PRODUCER_KEYS = ("producer", "emitter", "reporter")
_PRODUCER_VERSION_KEYS = ("producerVersion", "producer_version")

# Auxiliary provider token fields are preserved verbatim for provenance but
# are never added to ActualRunTokens.
_AUX_FIELD_SUFFIX = "Tokens"
_CANONICAL_TOKEN_KEYS = frozenset(_INPUT_TOKEN_KEYS + _OUTPUT_TOKEN_KEYS + _TOTAL_TOKEN_KEYS)

_EXECUTED_MARKERS = {
    "PROVIDER_EXECUTED",
    "EXECUTED",
    "COMPLETED",
    "SUCCEEDED",
    "SUCCESS",
    "OK",
}
# A generic denial marker does NOT prove where in the execution path the
# denial happened — DENIED != proven denied-before-provider-execution.
_GENERIC_DENIED_MARKERS = {
    "DENIED",
    "REJECTED",
    "BLOCKED",
    "REFUSED",
}
_EXPLICIT_PRE_EXEC_DENIAL = {
    "DENIED_BEFORE_EXECUTION",
    "THROTTLED_BEFORE_DISPATCH",
}
# Only explicit dispatch evidence may establish DISPATCHED_PENDING — a
# generic TIMEOUT/PENDING could have occurred before dispatch.
_EXPLICIT_DISPATCHED_MARKERS = {
    "DISPATCHED",
    "DISPATCHED_PENDING",
    "IN_FLIGHT",
    "SENT",
}
_GENERIC_PENDING_MARKERS = {
    "TIMEOUT",
    "TIMED_OUT",
    "PENDING",
}
_FAILED_PREEXEC_MARKERS = {
    "FAILED_BEFORE_EXECUTION",
    "PRE_DISPATCH_FAILED",
    "DISPATCH_FAILED",
    "REQUEST_INVALID",
}

# Explicit structured fields that prove the execution-path stage.
_PROVIDER_EXECUTED_FLAG_KEYS = ("providerExecuted", "provider_executed")
_PROVIDER_DISPATCHED_FLAG_KEYS = ("providerDispatched", "provider_dispatched")
_DENIED_BEFORE_EXEC_FLAG_KEYS = ("deniedBeforeExecution", "denied_before_execution")
_STAGE_KEYS = ("stage", "executionStage", "execution_stage", "denialStage", "denial_stage")
_PRE_EXEC_STAGE_VALUES = {
    "PRE_PROVIDER",
    "PRE_EXECUTION",
    "PRE_DISPATCH",
    "BEFORE_DISPATCH",
    "PRE_EXEC",
}


def _is_usage_candidate(event: Mapping[str, Any]) -> bool:
    """A canonical event is a C16 candidate only when it carries explicit
    model-call identity, usage, or execution-state fields. Generic action
    events are never candidates."""
    attributes = event.get("attributes") or {}
    if not isinstance(attributes, Mapping):
        return False
    keys = set(attributes)
    return bool(
        keys
        & (
            set(_MODEL_CALL_ID_KEYS)
            | set(_PROVIDER_REQUEST_KEYS)
            | set(_INPUT_TOKEN_KEYS)
            | set(_OUTPUT_TOKEN_KEYS)
            | set(_TOTAL_TOKEN_KEYS)
            | set(_EXECUTION_STATE_KEYS)
        )
    )


def _int_or_none(value: Any) -> int | None:
    """Strict token normalization: real non-negative ints only. No coercion."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _marker(value: str) -> str:
    return value.strip().upper().replace("-", "_").replace(" ", "_")


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _falsey(value: Any) -> bool:
    return value is False or (isinstance(value, str) and value.strip().lower() == "false")


def _state_for_marker(marker: str, basis: str) -> tuple[str, str, list[str]]:
    """Map one status-style marker to an execution state — failing closed.

    Generic denial and generic timeout/pending markers do NOT establish the
    execution-path stage; they resolve to UNKNOWN with an explicit
    stage-not-established limitation rather than a fabricated zero or an
    assumed post-dispatch state.
    """
    if marker in EXECUTION_STATES:
        return marker, basis, []
    if marker in _EXECUTED_MARKERS:
        return "PROVIDER_EXECUTED", basis, []
    if marker in _EXPLICIT_PRE_EXEC_DENIAL:
        return "DENIED_BEFORE_EXECUTION", basis, []
    if marker in _FAILED_PREEXEC_MARKERS:
        return "FAILED_BEFORE_EXECUTION", basis, []
    if marker in _EXPLICIT_DISPATCHED_MARKERS:
        return "DISPATCHED_PENDING", basis, []
    if marker in _GENERIC_DENIED_MARKERS:
        return "UNKNOWN", basis, ["DENIAL_STAGE_NOT_ESTABLISHED"]
    if marker in _GENERIC_PENDING_MARKERS:
        return "UNKNOWN", basis, ["DISPATCH_STAGE_NOT_ESTABLISHED"]
    return "UNKNOWN", f"unrecognized:{basis}={marker}", [f"UNRECOGNIZED_EXECUTION_MARKER:{marker}"]


def _execution_state(
    attributes: Mapping[str, Any], *, usage_semantics_qualified: bool
) -> tuple[str, str | None, list[str]]:
    """Bounded execution-state derivation — explicit stage evidence only.

    Precedence: explicit ``executionState`` field, then explicit structured
    stage fields, then bounded status markers, then provider-emitted usage
    (a *qualified* token report implies the provider executed), else
    UNKNOWN. A bare generic ``FAILED``/``ERROR`` is UNKNOWN — it cannot
    prove whether execution occurred.
    """
    raw = _text(_first(attributes, _EXECUTION_STATE_KEYS))
    if raw:
        return _state_for_marker(_marker(raw), "explicit:executionState")

    # Explicit structured stage fields prove pre-provider denial or dispatch.
    if _truthy(_first(attributes, _DENIED_BEFORE_EXEC_FLAG_KEYS)):
        return "DENIED_BEFORE_EXECUTION", "explicit:deniedBeforeExecution", []
    stage = _text(_first(attributes, _STAGE_KEYS))
    if stage and _marker(stage) in _PRE_EXEC_STAGE_VALUES:
        return "DENIED_BEFORE_EXECUTION", "explicit:stage", []
    if _falsey(_first(attributes, _PROVIDER_EXECUTED_FLAG_KEYS)):
        return "DENIED_BEFORE_EXECUTION", "explicit:providerExecuted=false", []
    if _falsey(_first(attributes, _PROVIDER_DISPATCHED_FLAG_KEYS)):
        return "DENIED_BEFORE_EXECUTION", "explicit:providerDispatched=false", []

    denied = attributes.get("denied")
    if _truthy(denied):
        return "UNKNOWN", "generic-denial-no-stage:denied", ["DENIAL_STAGE_NOT_ESTABLISHED"]

    for key in _STATUS_KEYS:
        value = _text(attributes.get(key))
        if value is None:
            continue
        return _state_for_marker(_marker(value), f"field:{key}")
    if _first(attributes, _INPUT_TOKEN_KEYS + _OUTPUT_TOKEN_KEYS) is not None:
        # Provider-emitted usage proves execution only when the token
        # semantics themselves are qualified — an unqualified raw field named
        # ``inputTokens`` must not upgrade UNKNOWN into PROVIDER_EXECUTED.
        if usage_semantics_qualified:
            return "PROVIDER_EXECUTED", "provider-emitted-usage", []
        return (
            "UNKNOWN",
            "provider-emitted-usage-unqualified-token-semantics",
            ["USAGE_FIELDS_INSUFFICIENT_TO_PROVE_EXECUTION"],
        )
    if _truthy(_first(attributes, _PROVIDER_DISPATCHED_FLAG_KEYS)):
        return "DISPATCHED_PENDING", "explicit:providerDispatched=true", []
    return "UNKNOWN", None, []


def _execution_key(
    model_call_id: str | None,
    provider_request_id: str | None,
    attempt: int | None,
    provider: str | None = None,
) -> str | None:
    """Explicit execution identity — provider-scoped request id wins;
    otherwise the model call id scoped by its declared attempt. Provider
    request ids are only unique *within* a provider, so a known provider
    namespaces the key. Never timestamps."""
    if provider_request_id:
        scope = f"provider:{provider}|" if provider else ""
        return f"{scope}providerRequestId:{provider_request_id}"
    if model_call_id:
        suffix = str(attempt) if attempt is not None else "unspecified"
        return f"modelCallId:{model_call_id}#attempt:{suffix}"
    return None


def _field_of(attributes: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    """The exact native attribute name that supplied a fact, or None."""
    for key in keys:
        if attributes.get(key) not in (None, ""):
            return key
    return None


# Canonical C16 token field names — a record whose native fields are literally
# these names carries direct token semantics; every other field name is a
# raw alias that needs an explicit approved mapping or accounting profile.
_DIRECT_TOKEN_FIELDS = {"inputTokens", "outputTokens", "totalTokens"}
_PROFILE_SOURCE_KEYS = {
    "inputTokens": "inputTokenSourceField",
    "outputTokens": "outputTokenSourceField",
    "totalTokens": "totalTokenSourceField",
}
_TOKEN_QUAL_ORDER = {"UNKNOWN": 0, "PROVISIONAL": 1, "QUALIFIED": 2}


def _token_side_semantics(
    *,
    source_field: str | None,
    canonical_name: str,
    event_mapped: bool,
    approved_profile: Mapping[str, Any] | None,
    accounting_profile: Mapping[str, Any] | None,
    record_provider: str | None,
) -> tuple[str, str, str | None]:
    """Return ``(qualification, basis, accountingProfileRef)`` for one token
    side. EVENT_MAPPING_QUALIFIED != TOKEN_SEMANTICS_QUALIFIED — the event
    being mapped proves the record was parsed, not that this native field
    carries canonical input/output token semantics."""
    if source_field is None:
        return "UNKNOWN", "TOKEN_FIELD_ABSENT", None
    if accounting_profile:
        declared = _text(accounting_profile.get(_PROFILE_SOURCE_KEYS[canonical_name]))
        scoped = _text(accounting_profile.get("provider") or accounting_profile.get("producer"))
        provider_ok = scoped is None or scoped == record_provider
        if declared == source_field and provider_ok:
            ref = _text(accounting_profile.get("profileId")) or "unknown"
            return "QUALIFIED", f"TOKEN_ACCOUNTING_PROFILE:{ref}", ref
    if approved_profile:
        for mapping in approved_profile.get("fieldMappings") or ():
            if not isinstance(mapping, Mapping):
                continue
            if str(mapping.get("sourcePath") or "") != source_field:
                continue
            target = str(mapping.get("targetPath") or "").split(".")[-1]
            if target == canonical_name:
                return (
                    "QUALIFIED",
                    f"MAPPED_FIELD_SEMANTICS:{source_field}->{canonical_name}",
                    None,
                )
    if source_field == canonical_name:
        if event_mapped:
            return "QUALIFIED", "DIRECT_CANONICAL_FIELD_NAMES", None
        return "UNKNOWN", "CANONICAL_FIELD_WITHOUT_EVENT_MAPPING", None
    return "PROVISIONAL", "RAW_ALIAS_NOT_EXPLICITLY_QUALIFIED", None


def _source_role(state: str, has_usage_fields: bool) -> str:
    if state == "DENIED_BEFORE_EXECUTION":
        return "DENIAL_RECORD"
    if state == "FAILED_BEFORE_EXECUTION":
        return "PRE_EXECUTION_FAILURE_RECORD"
    if state == "DISPATCHED_PENDING":
        return "DISPATCH_RECORD"
    return "USAGE_TELEMETRY" if has_usage_fields else "EXECUTION_STATUS"


def _extract_record(
    event: Mapping[str, Any],
    *,
    approved_profiles: Mapping[str, Mapping[str, Any]] | None = None,
    token_accounting_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one canonical event into a ModelCallUsageRecord-shaped dict."""
    attributes = event.get("attributes") or {}
    raw_refs = event.get("rawRecordRefs") or ()
    artifact_id = None
    for ref in raw_refs:
        if isinstance(ref, Mapping) and ref.get("artifactId"):
            artifact_id = str(ref["artifactId"])
            break

    event_mapped = event.get("eventClassAssignment") == "MAPPED" and event.get("mappingProfileRef")
    approved_profile = (approved_profiles or {}).get(str(event.get("mappingProfileRef") or ""))
    provider = _text(_first(attributes, _PROVIDER_KEYS))

    # Token-field provenance — record exactly which native field supplied
    # each fact, then qualify the semantics per side.
    input_field = _field_of(attributes, _INPUT_TOKEN_KEYS)
    output_field = _field_of(attributes, _OUTPUT_TOKEN_KEYS)
    total_field = _field_of(attributes, _TOTAL_TOKEN_KEYS)
    side_bases: dict[str, str] = {}
    side_quals: dict[str, str] = {}
    accounting_ref: str | None = None
    for side, canonical_name, source_field in (
        ("input", "inputTokens", input_field),
        ("output", "outputTokens", output_field),
    ):
        qual, basis, ref = _token_side_semantics(
            source_field=source_field,
            canonical_name=canonical_name,
            event_mapped=bool(event_mapped),
            approved_profile=approved_profile,
            accounting_profile=token_accounting_profile,
            record_provider=provider,
        )
        side_quals[side] = qual
        side_bases[side] = basis
        accounting_ref = accounting_ref or ref
    sem_qual = min(
        (side_quals["input"], side_quals["output"]),
        key=lambda q: _TOKEN_QUAL_ORDER[q],
    )
    if side_bases["input"] == side_bases["output"]:
        token_basis = side_bases["input"]
    else:
        token_basis = f"input:{side_bases['input']}|output:{side_bases['output']}"

    state, state_basis, state_lims = _execution_state(
        attributes, usage_semantics_qualified=(sem_qual == "QUALIFIED")
    )
    input_tokens = _int_or_none(_first(attributes, _INPUT_TOKEN_KEYS))
    output_tokens = _int_or_none(_first(attributes, _OUTPUT_TOKEN_KEYS))
    total_tokens = _int_or_none(_first(attributes, _TOTAL_TOKEN_KEYS))
    attempt_raw = _first(attributes, _ATTEMPT_KEYS)
    attempt = (
        attempt_raw
        if isinstance(attempt_raw, int) and not isinstance(attempt_raw, bool) and attempt_raw >= 1
        else None
    )
    model_call_id = _text(_first(attributes, _MODEL_CALL_ID_KEYS))
    provider_request_id = _text(_first(attributes, _PROVIDER_REQUEST_KEYS))
    has_usage_fields = (
        _first(attributes, _INPUT_TOKEN_KEYS + _OUTPUT_TOKEN_KEYS + _TOTAL_TOKEN_KEYS) is not None
    )
    raw_token_fields = {
        str(k): attributes[k]
        for k in attributes
        if isinstance(k, str) and k.endswith(_AUX_FIELD_SUFFIX) and k not in _CANONICAL_TOKEN_KEYS
    }
    token_fields_present = {
        "inputTokens": input_field is not None,
        "outputTokens": output_field is not None,
        "totalTokens": total_field is not None,
    }
    limitations: list[str] = list(state_lims)

    record = {
        "recordSchemaVersion": USAGE_RECORD_SCHEMA,
        "runId": None,  # bound by reconcile_run_usage
        "modelCallId": model_call_id,
        "providerRequestId": provider_request_id,
        "agentId": _text(_first(attributes, _AGENT_KEYS)),
        "modelId": _text(_first(attributes, _MODEL_KEYS)),
        "provider": provider,
        "traceId": _text(_first(attributes, ("traceId", "trace_id"))),
        "requestId": _text(_first(attributes, ("requestId", "request_id"))),
        "sessionId": _text(_first(attributes, ("sessionId", "session_id"))),
        "taskId": _text(_first(attributes, ("taskId", "task_id"))),
        "attemptNumber": attempt,
        "retryOfModelCallId": _text(_first(attributes, _RETRY_OF_KEYS)),
        "executionState": state,
        "executionStateBasis": state_basis,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
        "startedAt": _text(_first(attributes, _STARTED_KEYS)),
        "completedAt": _text(_first(attributes, _COMPLETED_KEYS)),
        "sourceArtifactId": artifact_id,
        "sourceEventRef": str(event.get("eventId") or ""),
        "sourceEventRefs": [str(event.get("eventId") or "")],
        "sourceRole": _source_role(state, has_usage_fields),
        "producer": _text(_first(attributes, _PRODUCER_KEYS)),
        "producerVersion": _text(_first(attributes, _PRODUCER_VERSION_KEYS)),
        "mappingQualification": (
            "QUALIFIED"
            if event.get("eventClassAssignment") == "MAPPED" and event.get("mappingProfileRef")
            else "UNKNOWN"
        ),
        "inputTokenSourceField": input_field,
        "outputTokenSourceField": output_field,
        "totalTokenSourceField": total_field,
        "tokenSemanticQualification": sem_qual,
        "tokenSemanticBasis": token_basis,
        "tokenAccountingProfileRef": accounting_ref,
        "usageQualification": "UNKNOWN",
        "tokenFieldsPresent": token_fields_present,
        "rawTokenFields": raw_token_fields or None,
        "limitations": limitations,
    }
    return record


def _usage_qualification(record: dict[str, Any]) -> tuple[str, list[str]]:
    """QUALIFIED only when provider execution is established and both token
    sides are valid non-negative ints consistent with any declared total."""
    if record["executionState"] != "PROVIDER_EXECUTED":
        return "UNKNOWN", []
    in_tok, out_tok, tot_tok = record["inputTokens"], record["outputTokens"], record["totalTokens"]
    present = record["tokenFieldsPresent"]
    issues: list[str] = []
    if not present["inputTokens"] or not present["outputTokens"]:
        missing = [k for k in ("inputTokens", "outputTokens") if not present[k]]
        issues.append(f"USAGE_INCOMPLETE_MISSING:{','.join(missing)}")
        return "PROVISIONAL", issues
    if in_tok is None or out_tok is None:
        bad = [k for k, v in (("inputTokens", in_tok), ("outputTokens", out_tok)) if v is None]
        issues.append(f"USAGE_INVALID_NON_INTEGER:{','.join(bad)}")
        return "PROVISIONAL", issues
    if tot_tok is not None and tot_tok != in_tok + out_tok:
        issues.append("TOTAL_TOKEN_MISMATCH:input+output!=declaredTotal")
        return "PROVISIONAL", issues
    return "QUALIFIED", issues


def _merge_group(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Merge records sharing one explicit execution identity.

    Returns ``(merged_records, suppressed_count, limitations)``. Conflicting
    execution facts split the group instead of being silently merged.
    """
    limitations: list[str] = []
    # Conflicting non-null modelCallId, attemptNumber, or provider under one
    # execution key means the identity is not actually shared — split and
    # surface the uncertainty instead of silently merging.
    mc_ids = {r["modelCallId"] for r in records if r["modelCallId"]}
    attempts = {r["attemptNumber"] for r in records if r["attemptNumber"] is not None}
    providers = {r["provider"] for r in records if r["provider"]}
    if len(mc_ids) > 1 or len(attempts) > 1 or len(providers) > 1:
        limitations.append("POSSIBLE_DUPLICATE_IDENTITY_UNRESOLVED")
        merged: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        for r in records:
            key = (r["modelCallId"], r["attemptNumber"], r["provider"])
            if key in merged:
                merged[key]["sourceEventRefs"].extend(r["sourceEventRefs"])
            else:
                merged[key] = r
        return list(merged.values()), len(records) - len(merged), limitations

    base = dict(records[0])
    base["sourceEventRefs"] = [r["sourceEventRef"] for r in records]
    states = {r["executionState"] for r in records}
    tokens = {
        (r["inputTokens"], r["outputTokens"], r["totalTokens"])
        for r in records
        if r["executionState"] == "PROVIDER_EXECUTED"
    }
    if len(states) > 1:
        base["executionState"] = "UNKNOWN"
        base["executionStateBasis"] = "conflicting-source-states"
        limitations.append("EXECUTION_STATE_CONFLICT")
    if len(tokens) > 1:
        base["inputTokens"] = base["outputTokens"] = base["totalTokens"] = None
        base["tokenFieldsPresent"] = {
            "inputTokens": False,
            "outputTokens": False,
            "totalTokens": False,
        }
        limitations.append("TOKEN_VALUE_CONFLICT")
    for field in (
        "startedAt",
        "completedAt",
        "agentId",
        "modelId",
        "provider",
        "producer",
        "producerVersion",
        "retryOfModelCallId",
        "attemptNumber",
        "modelCallId",
        "traceId",
        "requestId",
        "sessionId",
        "taskId",
    ):
        if base.get(field) is None:
            base[field] = next((r[field] for r in records if r.get(field) is not None), None)
    raw_aux: dict[str, Any] = {}
    for r in records:
        raw_aux.update(r.get("rawTokenFields") or {})
    base["rawTokenFields"] = raw_aux or None
    for r in records:
        for item in r["limitations"]:
            if item not in base["limitations"]:
                base["limitations"].append(item)
    return [base], len(records) - 1, limitations


def reconcile_run_usage(
    *,
    run_resolution: Mapping[str, Any],
    canonical_events: Sequence[Mapping[str, Any]],
    expected_agent_ids: Sequence[str] | None = None,
    approved_profiles: Mapping[str, Mapping[str, Any]] | None = None,
    token_accounting_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile every model-call usage candidate against the resolved run.

    Pure function over the run resolution plus the analysis snapshot's
    canonical events — deterministic, no clock, no AI.
    """
    qualified = {str(r) for r in run_resolution.get("qualifiedEventRefs") or ()}
    ambiguous = {str(r) for r in run_resolution.get("ambiguousEvidenceRefs") or ()}
    run_id = str(run_resolution.get("runId") or "")

    # Identifier values observed on the run's qualified events plus the
    # operator-declared identifier sets — the explicit "could belong to this
    # run" test for ambiguous evidence.
    run_identifier_values: dict[str, set[str]] = {}
    for kind, values in (run_resolution.get("identifiers") or {}).items():
        run_identifier_values[str(kind)] = {str(v) for v in values}
    declaration = run_resolution.get("declaration") or {}
    declared_ids = declared_identifier_sets(declaration) if declaration.get("runId") else {}
    for kind, values in declared_ids.items():
        run_identifier_values.setdefault(str(kind), set()).update(str(v) for v in values)

    bound_events: list[Mapping[str, Any]] = []
    ambiguous_candidates: list[str] = []
    unresolved_candidates: list[str] = []
    foreign_candidates: list[str] = []
    for event in canonical_events:
        ref = str(event.get("eventId") or "")
        if not ref or not _is_usage_candidate(event):
            continue
        if ref in qualified:
            bound_events.append(event)
        elif ref in ambiguous:
            # The resolver also surfaces evidence bound to a DIFFERENT run as
            # ambiguous-for-this-run. A record is genuinely ambiguous for C16
            # only when it could belong to this run: it claims this runId
            # among conflicting run ids, or it shares an identifier value with
            # the run's qualified/declared identifier sets. A record carrying
            # only a foreign run binding and sharing nothing is provably
            # another run's call — excluded as context, never blocking.
            ids = event_identifiers(event, declared_kinds=declared_ids.keys())
            claims = {str(v) for v in ids.get("runId", ())} | {
                str(v) for v in ids.get("scenarioRunId", ())
            }
            shares = any(
                {str(v) for v in values} & run_identifier_values.get(kind, set())
                for kind, values in ids.items()
            )
            if claims and run_id not in claims and not shares:
                foreign_candidates.append(ref)
            else:
                ambiguous_candidates.append(ref)
        else:
            unresolved_candidates.append(ref)

    # ---- execution identity / dedup ----------------------------------------
    groups: dict[str, list[dict[str, Any]]] = {}
    identity_absent: list[dict[str, Any]] = []
    request_scopes: dict[str, set[str | None]] = {}
    for event in bound_events:
        record = _extract_record(
            event,
            approved_profiles=approved_profiles,
            token_accounting_profile=token_accounting_profile,
        )
        key = _execution_key(
            record["modelCallId"],
            record["providerRequestId"],
            record["attemptNumber"],
            record["provider"],
        )
        if key is None:
            record["limitations"].append("EXECUTION_IDENTITY_ABSENT")
            identity_absent.append(record)
        else:
            groups.setdefault(key, []).append(record)
            if record["providerRequestId"]:
                request_scopes.setdefault(record["providerRequestId"], set()).add(
                    record["provider"]
                )

    # A request id shared between provider-scoped and provider-absent records
    # cannot be proven one execution or two — never silently merged; the
    # identity uncertainty blocks a definitive total.
    request_scope_conflict = any(
        None in scopes and len(scopes) > 1 for scopes in request_scopes.values()
    )

    duplicate_groups: list[dict[str, Any]] = []
    limitations: list[str] = []
    suppressed = 0
    records: list[dict[str, Any]] = []
    for key, members in sorted(groups.items()):
        merged, dropped, notes = _merge_group(members)
        suppressed += dropped
        limitations.extend(notes)
        if dropped:
            duplicate_groups.append(
                {
                    "executionKey": key,
                    "eventRefs": sorted(r["sourceEventRef"] for r in members),
                    "suppressedTelemetryRecords": dropped,
                }
            )
        records.extend(merged)
    if len(identity_absent) > 1 or request_scope_conflict:
        limitations.append("POSSIBLE_DUPLICATE_IDENTITY_UNRESOLVED")
    records.extend(identity_absent)
    records.sort(key=lambda r: (str(r["sourceArtifactId"]), str(r["sourceEventRef"])))

    # ---- qualification ------------------------------------------------------
    for record in records:
        record["runId"] = str(run_resolution.get("runId") or "")
        qual, issues = _usage_qualification(record)
        record["usageQualification"] = qual
        record["limitations"].extend(issues)

    executed = [r for r in records if r["executionState"] == "PROVIDER_EXECUTED"]
    # A call enters the assessed total only when execution is proven, the
    # token VALUES are valid, the token FIELD SEMANTICS are qualified, and
    # the event mapping/run membership is qualified — three separate
    # qualifications, never collapsed.
    counted = [
        r
        for r in executed
        if r["usageQualification"] == "QUALIFIED"
        and r["tokenSemanticQualification"] == "QUALIFIED"
        and r["mappingQualification"] == "QUALIFIED"
    ]
    unqualified_usage = [r for r in executed if r["usageQualification"] != "QUALIFIED"]
    unqualified_token = [
        r
        for r in executed
        if r["tokenSemanticQualification"] != "QUALIFIED" and r["usageQualification"] == "QUALIFIED"
    ]
    missing_usage = [
        r
        for r in executed
        if r["usageQualification"] != "QUALIFIED"
        and any(str(lim).startswith("USAGE_INCOMPLETE_MISSING") for lim in r["limitations"])
    ]
    unqualified_mapping = [r for r in records if r["mappingQualification"] != "QUALIFIED"]
    denied = [r for r in records if r["executionState"] == "DENIED_BEFORE_EXECUTION"]
    failed_pre = [r for r in records if r["executionState"] == "FAILED_BEFORE_EXECUTION"]
    pending = [r for r in records if r["executionState"] == "DISPATCHED_PENDING"]
    unknown_exec = [r for r in records if r["executionState"] == "UNKNOWN"]

    for r in records:
        r["contributesToActual"] = r in counted

    # ---- retries ------------------------------------------------------------
    # A retry that reached the provider counts as a real execution even when
    # its usage is incomplete — lineage comes only from explicit evidence.
    retries = [r for r in executed if (r["attemptNumber"] or 0) > 1 or r["retryOfModelCallId"]]
    by_call: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r["modelCallId"]:
            by_call.setdefault(r["modelCallId"], []).append(r)
    retry_lineage_unresolved = 0
    for call_id, members in sorted(by_call.items()):
        distinct_execs = {
            _execution_key(
                m["modelCallId"], m["providerRequestId"], m["attemptNumber"], m["provider"]
            )
            for m in members
        }
        has_lineage = any((m["attemptNumber"] or 0) > 1 or m["retryOfModelCallId"] for m in members)
        if len(distinct_execs) > 1 and not has_lineage:
            # Distinct proven executions count regardless of whether they are
            # a retry, a repeated logical action, or an independent repeat —
            # all incurred actual provider usage. The unknown relation is
            # surfaced as provenance, but never erases the token total.
            limitations.append(f"RETRY_RELATION_UNRESOLVED:{call_id}")
            retry_lineage_unresolved += len(distinct_execs)

    # ---- totals (counted records only) ---------------------------------------
    total_in = sum(int(r["inputTokens"]) for r in counted)
    total_out = sum(int(r["outputTokens"]) for r in counted)
    participating = sorted({str(r["agentId"]) for r in counted if r["agentId"]})
    if any(r["agentId"] is None for r in counted):
        limitations.append("COUNTED_CALL_WITHOUT_AGENT_IDENTITY")

    per_agent: dict[str, dict[str, Any]] = {}
    per_provider: dict[str, dict[str, Any]] = {}
    per_model: dict[str, dict[str, Any]] = {}

    def _acc(bucket: dict[str, dict[str, Any]], key: str | None, r: dict[str, Any]) -> None:
        label = key or "UNATTRIBUTED"
        row = bucket.setdefault(
            label,
            {
                "providerExecutedCalls": 0,
                "retryExecutions": 0,
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
            },
        )
        row["providerExecutedCalls"] += 1
        row["inputTokens"] += int(r["inputTokens"])
        row["outputTokens"] += int(r["outputTokens"])
        row["totalTokens"] += int(r["inputTokens"]) + int(r["outputTokens"])
        if (r["attemptNumber"] or 0) > 1 or r["retryOfModelCallId"]:
            row["retryExecutions"] += 1

    for r in counted:
        _acc(per_agent, r["agentId"], r)
        _acc(per_provider, r["provider"], r)
        _acc(per_model, r["modelId"], r)

    agent_rows = [{"agentId": k, **v} for k, v in sorted(per_agent.items())]
    provider_rows = [
        {
            "provider": k,
            "executedCalls": v["providerExecutedCalls"],
            "inputTokens": v["inputTokens"],
            "outputTokens": v["outputTokens"],
            "totalTokens": v["totalTokens"],
        }
        for k, v in sorted(per_provider.items())
    ]
    model_rows = [
        {
            "modelId": k,
            "executedCalls": v["providerExecutedCalls"],
            "inputTokens": v["inputTokens"],
            "outputTokens": v["outputTokens"],
            "totalTokens": v["totalTokens"],
        }
        for k, v in sorted(per_model.items())
    ]

    # ---- expected participant set -------------------------------------------
    expected_block: dict[str, Any] | None = None
    missing_expected: list[str] = []
    if expected_agent_ids is not None:
        declared = sorted({str(a).strip() for a in expected_agent_ids if str(a).strip()})
        missing_expected = [a for a in declared if a not in participating]
        unexpected = [a for a in participating if a not in declared]
        expected_block = {
            "expectedAgents": declared,
            "observedAgents": participating,
            "missingExpectedAgents": missing_expected,
            "unexpectedAgents": unexpected,
        }
        if missing_expected:
            limitations.append(
                "EXPECTED_AGENT_WITHOUT_USAGE_EVIDENCE:" + ",".join(missing_expected)
            )
    else:
        limitations.append("EXPECTED_AGENT_SET_NOT_DECLARED")

    if ambiguous_candidates:
        limitations.append(f"AMBIGUOUS_RUN_MEMBERSHIP_CALLS:{len(ambiguous_candidates)}")
    if foreign_candidates:
        limitations.append(f"FOREIGN_RUN_USAGE_EXCLUDED:{len(foreign_candidates)}")
    if unresolved_candidates:
        limitations.append(f"UNRESOLVED_RUN_MEMBERSHIP_CALLS:{len(unresolved_candidates)}")
    if unqualified_mapping:
        limitations.append(f"UNQUALIFIED_MAPPING_CALLS:{len(unqualified_mapping)}")
    if unqualified_token:
        limitations.append(f"TOKEN_SEMANTICS_NOT_QUALIFIED:{len(unqualified_token)}")
    if missing_usage:
        limitations.append(f"EXECUTED_CALLS_MISSING_USAGE:{len(missing_usage)}")
    if pending:
        limitations.append(f"DISPATCHED_CALLS_UNRESOLVED:{len(pending)}")
    if unknown_exec:
        limitations.append(f"UNKNOWN_EXECUTION_STATE_CALLS:{len(unknown_exec)}")

    # ---- measurement state ----------------------------------------------------
    any_candidates = bool(records or ambiguous_candidates or unresolved_candidates)
    complete = (
        bool(records)
        and not unqualified_usage
        and not unqualified_token
        and not unqualified_mapping
        and not pending
        and not unknown_exec
        and not ambiguous_candidates
        and not unresolved_candidates
        and not missing_expected
        and not any("POSSIBLE_DUPLICATE_IDENTITY_UNRESOLVED" in lim for lim in limitations)
    )
    if not any_candidates or not records:
        state = "NOT_MEASURED"
    elif complete:
        state = "MEASURED"
    else:
        state = "PARTIAL"

    actual = (total_in + total_out) if state == "MEASURED" else None

    return {
        "schemaVersion": CONTROL16_MEASUREMENT_SCHEMA,
        "controlCode": CONTROL16_CODE,
        "runId": str(run_resolution.get("runId") or ""),
        "measurementState": state,
        "expectedAgentIds": list(expected_agent_ids) if expected_agent_ids is not None else None,
        "expectedAgents": expected_block,
        "participatingAgents": participating,
        "providerExecutedCalls": len(executed),
        "countedCalls": len(counted),
        "retryExecutions": len(retries),
        "retryLineageUnresolvedCalls": retry_lineage_unresolved,
        "deniedBeforeExecutionCalls": len(denied),
        "failedBeforeExecutionCalls": len(failed_pre),
        "pendingCalls": len(pending),
        "unknownExecutionCalls": len(unknown_exec),
        "duplicateTelemetryRecordsSuppressed": suppressed,
        "qualifiedUsageCalls": len(counted),
        "unqualifiedUsageCalls": len(unqualified_usage),
        "missingUsageCalls": len(missing_usage),
        "unqualifiedMappingCalls": len(unqualified_mapping),
        "tokenSemanticsUnqualifiedCalls": len(unqualified_token),
        "ambiguousRunCalls": len(ambiguous_candidates),
        "unresolvedRunCalls": len(unresolved_candidates),
        "totalInputTokens": total_in,
        "totalOutputTokens": total_out,
        "actualRunTokens": actual,
        "knownQualifiedInputTokens": total_in,
        "knownQualifiedOutputTokens": total_out,
        "knownQualifiedTokens": total_in + total_out,
        "perAgentBreakdown": agent_rows,
        "perProviderBreakdown": provider_rows,
        "perModelBreakdown": model_rows,
        "usageRecords": records,
        "duplicateGroups": duplicate_groups,
        "excludedEvidence": {
            "ambiguousRunRefs": sorted(ambiguous_candidates),
            "foreignRunRefs": sorted(foreign_candidates),
            "unresolvedRunRefs": sorted(unresolved_candidates),
            "deniedBeforeExecutionRefs": sorted(r["sourceEventRef"] for r in denied),
            "failedBeforeExecutionRefs": sorted(r["sourceEventRef"] for r in failed_pre),
            "pendingRefs": sorted(r["sourceEventRef"] for r in pending),
            "unqualifiedUsageRefs": sorted(r["sourceEventRef"] for r in unqualified_usage),
            "unqualifiedMappingRefs": sorted(r["sourceEventRef"] for r in unqualified_mapping),
        },
        "evidenceRefs": sorted(
            {r["sourceEventRef"] for r in records}
            | set(ambiguous_candidates)
            | set(unresolved_candidates)
        ),
        "limitations": sorted(set(limitations)),
        "verdict": None,
        "verdictOwner": "HAIEC",
    }
