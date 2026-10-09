"""Deterministic application-level analysis composition.

This package composes existing canonical owners. It does not define a parallel
truth model and does not depend on AI.
"""

from logsense.forensics.reporting import build_report_from_analysis

from .spine import (
    ArtifactEvidence,
    ContextLineageInstruction,
    DelegatedActionIntegrityInstruction,
    EffectEnvelopeInstruction,
    GuardrailMediationInstruction,
    OtlpLogEvidence,
    OtlpMetricEvidence,
    OtlpTraceEvidence,
    RecoveryInstruction,
    SourceContradictionInstruction,
    StateBindingInstruction,
    analyze_artifacts,
)

__all__ = ["ArtifactEvidence", "ContextLineageInstruction", "DelegatedActionIntegrityInstruction", "EffectEnvelopeInstruction", "GuardrailMediationInstruction", "OtlpLogEvidence", "OtlpMetricEvidence", "OtlpTraceEvidence", "RecoveryInstruction", "SourceContradictionInstruction", "StateBindingInstruction", "analyze_artifacts", "build_report_from_analysis"]
