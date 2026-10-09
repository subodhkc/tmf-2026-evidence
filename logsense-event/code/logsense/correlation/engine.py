"""
Correlation Engine
Cross-file association using explicit IDs and temporal proximity.

Semantic boundary: correlation is an association signal only. A shared identifier or
temporal window does not establish causal order, root cause, action application, or
any Phase 8.7 forensic truth state.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from logsense.models.events import CanonicalEvent, LogType


@dataclass
class CorrelationGroup:
    """A group of associated events across files.

    Membership records a correlation basis; it is not a causal edge.
    """

    correlation_id: str
    correlation_type: str  # request_id, session_id, trace_id, temporal
    events: list[CanonicalEvent] = field(default_factory=list)

    files_involved: set[str] = field(default_factory=set)
    log_types_involved: set[LogType] = field(default_factory=set)

    time_span_seconds: float = 0.0

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def is_cross_file(self) -> bool:
        return len(self.files_involved) > 1

    @property
    def is_cross_type(self) -> bool:
        return len(self.log_types_involved) > 1

    def add_event(self, event: CanonicalEvent) -> None:
        self.events.append(event)
        self.files_involved.add(event.source)
        self.log_types_involved.add(event.log_type)

        if len(self.events) > 1:
            timestamps = [e.timestamp for e in self.events]
            self.time_span_seconds = (max(timestamps) - min(timestamps)).total_seconds()


@dataclass
class CorrelationResult:
    """Result of correlation analysis."""

    groups: list[CorrelationGroup] = field(default_factory=list)

    total_events: int = 0
    correlated_events: int = 0
    uncorrelated_events: int = 0

    cross_file_groups: int = 0
    cross_type_groups: int = 0

    @property
    def correlation_rate(self) -> float:
        if self.total_events == 0:
            return 0.0
        return self.correlated_events / self.total_events

    def get_groups_by_type(self, correlation_type: str) -> list[CorrelationGroup]:
        return [g for g in self.groups if g.correlation_type == correlation_type]


class CorrelationEngine:
    """
    Engine for correlating events across files and log types.

    Correlation methods:
    1. Request ID matching (request_id, x-request-id, etc.)
    2. Session ID matching
    3. Trace ID matching (distributed tracing)
    4. Temporal proximity (events within time window)
    """

    TEMPORAL_WINDOW_SECONDS = 5.0

    def __init__(self, temporal_window: float = 5.0):
        self.temporal_window = temporal_window

    def correlate(self, events: list[CanonicalEvent]) -> CorrelationResult:
        """
        Correlate events across files.

        Args:
            events: All events from all files

        Returns:
            CorrelationResult with correlation groups
        """
        if not events:
            return CorrelationResult()

        groups: dict[str, CorrelationGroup] = {}
        correlated_event_ids: set[str] = set()

        id_groups = self._correlate_by_ids(events)
        for group in id_groups:
            groups[group.correlation_id] = group
            for event in group.events:
                correlated_event_ids.add(event.id)

        uncorrelated = [e for e in events if e.id not in correlated_event_ids]
        temporal_groups = self._correlate_by_temporal(uncorrelated)
        for group in temporal_groups:
            groups[group.correlation_id] = group
            for event in group.events:
                correlated_event_ids.add(event.id)

        all_groups = list(groups.values())

        return CorrelationResult(
            groups=all_groups,
            total_events=len(events),
            correlated_events=len(correlated_event_ids),
            uncorrelated_events=len(events) - len(correlated_event_ids),
            cross_file_groups=sum(1 for g in all_groups if g.is_cross_file),
            cross_type_groups=sum(1 for g in all_groups if g.is_cross_type),
        )

    def _correlate_by_ids(self, events: list[CanonicalEvent]) -> list[CorrelationGroup]:
        """Correlate events by shared IDs (request_id, session_id, etc.)."""
        id_to_events: dict[tuple[str, str], list[CanonicalEvent]] = defaultdict(list)

        for event in events:
            for id_type, id_value in event.correlation_ids.items():
                if id_value:
                    key = (id_type, id_value)
                    id_to_events[key].append(event)

        groups = []
        for (id_type, id_value), group_events in id_to_events.items():
            if len(group_events) >= 2:
                group = CorrelationGroup(
                    correlation_id=f"{id_type}:{id_value}",
                    correlation_type=id_type,
                )
                for event in group_events:
                    group.add_event(event)
                groups.append(group)

        return groups

    def _correlate_by_temporal(
        self,
        events: list[CanonicalEvent],
    ) -> list[CorrelationGroup]:
        """Associate events by temporal proximity without inferring causal order."""
        if len(events) < 2:
            return []

        sorted_events = sorted(events, key=lambda e: e.timestamp)

        groups = []
        current_group: CorrelationGroup | None = None

        for event in sorted_events:
            if current_group is None:
                current_group = CorrelationGroup(
                    correlation_id=f"temporal:{event.id}",
                    correlation_type="temporal",
                )
                current_group.add_event(event)
            else:
                last_event = current_group.events[-1]
                time_diff = (event.timestamp - last_event.timestamp).total_seconds()

                if time_diff <= self.temporal_window:
                    current_group.add_event(event)
                else:
                    if current_group.event_count >= 2:
                        groups.append(current_group)

                    current_group = CorrelationGroup(
                        correlation_id=f"temporal:{event.id}",
                        correlation_type="temporal",
                    )
                    current_group.add_event(event)

        if current_group and current_group.event_count >= 2:
            groups.append(current_group)

        return groups

    def find_related_events(
        self,
        anchor_event: CanonicalEvent,
        all_events: list[CanonicalEvent],
        max_results: int = 10,
    ) -> list[CanonicalEvent]:
        """
        Find events related to an anchor event.

        Args:
            anchor_event: The event to find relations for
            all_events: All available events
            max_results: Maximum number of related events to return

        Returns:
            List of related events, sorted by relevance
        """
        related = []

        for event in all_events:
            if event.id == anchor_event.id:
                continue

            score = 0

            for id_type, id_value in anchor_event.correlation_ids.items():
                if id_value and event.correlation_ids.get(id_type) == id_value:
                    score += 10

            time_diff = abs(
                (event.timestamp - anchor_event.timestamp).total_seconds()
            )
            if time_diff <= self.temporal_window:
                score += 5
            elif time_diff <= self.temporal_window * 2:
                score += 2

            if event.source == anchor_event.source:
                score += 1

            if score > 0:
                related.append((score, event))

        related.sort(key=lambda x: -x[0])
        return [event for _, event in related[:max_results]]
