from __future__ import annotations

from collections.abc import Sequence


def project_context_lineage_item(
    *,
    context_item_ref: str,
    origin: str,
    source_authority: str,
    mutability: str,
    validation_state: str,
    integrity_state: str,
    temporal_basis: str,
    model_visible: bool | None,
    explicitly_referenced: bool | None,
    retrieved_at: str | None = None,
    evidence_refs: Sequence[str] = (),
    influence_evidence_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict:
    """Project context provenance without equating presence with influence.

    Retrieval, memory reads, model visibility, or user control do not establish
    that the model used the item. Influence becomes ESTABLISHED only when the
    caller provides explicit evidence bound to that influence claim.
    """
    influence_refs = list(dict.fromkeys(str(x) for x in influence_evidence_refs))
    influence_state = "ESTABLISHED" if influence_refs else "UNKNOWN"
    refs = list(dict.fromkeys([
        *(str(x) for x in evidence_refs),
        *influence_refs,
    ]))
    return {
        "contextItemRef": context_item_ref,
        "origin": origin,
        "sourceAuthority": source_authority,
        "mutability": mutability,
        "validationState": validation_state,
        "integrityState": integrity_state,
        "temporalBasis": temporal_basis,
        "modelVisible": model_visible,
        "explicitlyReferenced": explicitly_referenced,
        "influenceState": influence_state,
        "evidenceRefs": refs,
        "limitations": list(dict.fromkeys(str(x) for x in limitations)),
        **({"retrievedAt": retrieved_at} if retrieved_at is not None else {}),
    }
