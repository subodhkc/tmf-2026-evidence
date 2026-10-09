"""Forensic time-window filtering over canonical timeline rows.

Pure deterministic filtering — no new query engine, no new evidence store.
The filter matches on canonical event time (``normalizedTime``/``eventTime``),
never on analysis or evaluation creation time.

Clock safety: matching records that span more than one distinct clock domain
are flagged ``CROSS-CLOCK COMPARABILITY NOT ESTABLISHED``; no skew correction
is ever invented. Rows without a qualified/parseable event time are never
silently dropped — they are counted as excluded-unknown-time.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

SCHEMA = "forensic-window/0.1"

_COPY = {
    "banner": "TIME-WINDOW FORENSIC VIEW — NO CONTROL VERDICT",
    "ordering": (
        "Displayed sequence reflects canonical timeline ordering. "
        "Sequence does not establish causality."
    ),
    "crossClock": "CROSS-CLOCK COMPARABILITY NOT ESTABLISHED",
    "unknownTime": (
        "excluded — no qualified/parseable event time (records exist; "
        "they are not silently dropped)"
    ),
}


def forensic_window_copy() -> dict[str, str]:
    return dict(_COPY)


def _parse(value: Any) -> datetime | None:
    """Parse a canonical event time. Timezone-less values are not assumed —
    the same rule the temporal normalization spine applies."""
    if value in (None, ""):
        return None
    try:
        parsed = date_parser.isoparse(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _parse_bound(value: Any, label: str) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = _parse(value)
    if parsed is None:
        raise ValueError(f"{label} is not a qualified timestamp: {value}")
    return parsed


def _matches_identity(row: Mapping[str, Any], identity: str | None) -> bool:
    """Substring match against identity fields already present in the
    canonical projection — run/correlation refs only if they are already
    projected (``actionGroupRef``, ``eventRef``)."""
    if not identity:
        return True
    needle = identity.strip().lower()
    if not needle:
        return True
    haystacks = [
        row.get("actionGroupRef"),
        row.get("eventRef"),
        row.get("timelineEventId"),
    ]
    return any(needle in str(h).lower() for h in haystacks if h)


def _matches_source(row: Mapping[str, Any], source: str | None) -> bool:
    """Match against source refs already present in the projected row."""
    if not source:
        return True
    needle = source.strip().lower()
    if not needle:
        return True
    haystacks = list(row.get("sourceRefs") or ()) + list(row.get("evidenceRefs") or ())
    return any(needle in str(h).lower() for h in haystacks)


def forensic_window_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    from_time: Any = None,
    to_time: Any = None,
    identity: Any = None,
    source: Any = None,
) -> dict[str, Any]:
    """Filter canonical timeline rows into a forensic time window.

    Returns matched rows (canonical order preserved), the excluded
    unknown-time count, and the clock-domain comparability state. Raises
    ``ValueError`` on an unparseable filter bound — operator input errors
    fail loudly, never silently widen the window.
    """
    start = _parse_bound(from_time, "from")
    end = _parse_bound(to_time, "to")
    if start and end and start > end:
        raise ValueError("from timestamp is after the to timestamp")

    matched: list[dict[str, Any]] = []
    unknown_time = 0
    for row in rows:
        if not _matches_identity(row, identity) or not _matches_source(row, source):
            continue
        event_dt = _parse(row.get("normalizedTime") or row.get("eventTime"))
        if event_dt is None:
            unknown_time += 1
            continue
        if start and event_dt < start:
            continue
        if end and event_dt > end:
            continue
        matched.append(dict(row))

    domains = sorted(
        {str(r.get("clockDomainRef")) for r in matched if r.get("clockDomainRef")}
    )
    return {
        "schemaVersion": SCHEMA,
        "from": start.isoformat().replace("+00:00", "Z") if start else None,
        "to": end.isoformat().replace("+00:00", "Z") if end else None,
        "matchedCount": len(matched),
        "excludedUnknownTime": unknown_time,
        "rows": matched,
        "clockDomains": domains,
        # Comparable only when every matched row shares one declared clock
        # domain (or nothing matched). Missing or multiple domains = not
        # established — the UI surfaces the warning, never a correction.
        "crossClockEstablished": not matched
        or (
            len(domains) == 1
            and all(r.get("clockDomainRef") for r in matched)
        ),
        "copy": forensic_window_copy(),
    }
