"""TM Forum / AT&T competition control descriptors.

These cards describe what each control asks plus the capability truth:
all three LogSense measurement engines are AVAILABLE and all three HAIEC
Control Tests are technically AVAILABLE — event assessed is NOT YET for all
three (see ``competition.guidance`` — ``CAPABILITY_TRUTH`` is the single
owner of those flags; AVAILABLE != EVENT ASSESSED). The UI must never
fabricate a PASS/FAIL/SATISFIED verdict — HAIEC owns governance outcomes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from logsense.competition.guidance import CAPABILITY_TRUTH

# Measurement states the competition layer may emit. ENGINE_PLANNED is the
# only state shipped in R4; the rest are reserved for the R5 evaluators so UI
# copy does not have to change when they land.
MEASUREMENT_STATES = (
    "ENGINE_PLANNED",  # extension point exists; no measurement yet
    "NOT_MEASURED",  # engine exists, prerequisites missing
    "MEASURED",  # deterministic measurement emitted
)


@dataclass(frozen=True)
class CompetitionControl:
    """One competition control card descriptor."""

    control_number: int
    control_code: str
    name: str
    plain_question: str
    measurement_status: str = "ENGINE_PLANNED"
    note: str = ""

    def card(self) -> dict[str, str | int]:
        data = asdict(self)
        notes = {
            "ENGINE_PLANNED": "Measurement engine coming in the next competition build",
            "NOT_MEASURED": "Engine ready — declare a run and an expected-event manifest to measure",
        }
        data["cardNote"] = self.note or notes.get(self.measurement_status, "")
        truth = next(
            (c for c in CAPABILITY_TRUTH["controls"] if c["controlCode"] == self.control_code),
            None,
        )
        data["logsense_status"] = (truth or {}).get("logsenseMeasurement", "AVAILABLE")
        data["haiec_status"] = (truth or {}).get("haiecControlTest", "UNKNOWN")
        return data


COMPETITION_CONTROLS: tuple[CompetitionControl, ...] = (
    CompetitionControl(
        control_number=7,
        control_code="AIA-LOG-001",
        name="Event Recording",
        plain_question=(
            "Did the expected events get recorded, and were the timing gaps "
            "within the declared requirement?"
        ),
        measurement_status="NOT_MEASURED",
    ),
    CompetitionControl(
        control_number=9,
        control_code="AIA-ARC-006",
        name="Drift & Performance",
        plain_question=(
            "How did the selected runtime KPI change from its baseline across "
            "comparable measurement windows?"
        ),
        measurement_status="NOT_MEASURED",
        note=(
            "Engine ready — bind a metric profile, map the real KPI fields, "
            "and select an evidence-bound baseline. LogSense reports the "
            "measured change; HAIEC owns the governing baseline/threshold "
            "and the final result."
        ),
    ),
    CompetitionControl(
        control_number=16,
        control_code="ACN-COST-001",
        name="Spend Cap",
        plain_question=(
            "How many tokens did every provider-executed model call — all "
            "agents, all genuine retries — actually consume in this run?"
        ),
        measurement_status="NOT_MEASURED",
        note=(
            "Engine ready — declare a run with model-call usage evidence to "
            "reconcile. LogSense reports ActualRunTokens only; HAIEC owns the cap."
        ),
    ),
)


def control_cards() -> list[dict[str, str | int]]:
    return [control.card() for control in COMPETITION_CONTROLS]
