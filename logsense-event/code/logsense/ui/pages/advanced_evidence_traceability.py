from __future__ import annotations

import json

import streamlit as st

from logsense.presentation import evidence_card_rows, forensic_claim_rows

st.set_page_config(page_title="LogSense — Evidence Traceability", layout="wide")
st.title("Forensic Claims / Evidence Cards")
st.caption(
    "Traceability read layer over deterministic owners. Evidence cards resolve membership; they do not create stronger claims."
)

upload = st.file_uploader("Deterministic forensic report JSON", type=["json"], key="claims_report")
if upload is None:
    st.info("Load deterministic report JSON to inspect claims and evidence membership.")
    st.stop()

try:
    report = json.loads(upload.getvalue().decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    st.error(f"Invalid JSON: {exc}")
    st.stop()

if not isinstance(report, dict):
    st.error("Expected one report JSON object.")
    st.stop()

claims = forensic_claim_rows(report)
cards = {str(row.get("claimId")): row for row in evidence_card_rows(report)}

if not claims:
    st.info("No ForensicClaim records are present in this report.")
    st.stop()

for claim in claims:
    label = str(claim.get("statement") or claim.get("claimId") or "Claim")
    with st.expander(label):
        left, right = st.columns(2)
        with left:
            st.write("Claim class:", claim.get("claimClass") or "GENERIC")
            st.write("Evidence state:", claim["evidenceState"]["label"])
            st.write("Evidence strength:", claim.get("evidenceStrength") or "MISSING")
            st.write("Currentness:", claim["currentness"]["label"])
            st.write("Scope completeness:", claim["scopeCompleteness"]["label"])
            st.write("Independent source families:", claim.get("independentSourceFamilyCount"))
            st.write("Canonical owner:", claim.get("canonicalOwner"))
        with right:
            st.write("Evidence refs:", claim.get("evidenceRefs") or [])
            st.write("Strength basis:", claim.get("strengthBasis") or [])
            st.write("Not claimed:", claim.get("notClaimed") or [])
            st.write("Close with:", claim.get("closeWith") or [])
            st.write("Limitations:", claim.get("limitations") or [])

        card = cards.get(str(claim.get("claimId") or ""))
        if card is None:
            st.warning("No EvidenceCard is attached to this claim.")
            continue
        st.markdown("#### Evidence card")
        a, b, c = st.columns(3)
        a.metric("Members", card["memberCount"])
        b.metric("Resolved", card["resolvedCount"])
        c.metric("Orphan refs", card["orphanCount"])
        st.write("Membership digest:", f"`{card.get('membershipDigest')}`")
        if card["sources"]:
            st.dataframe(card["sources"], use_container_width=True)
        if card["orphanRefs"]:
            st.warning(
                "Orphan evidence references remain unresolved; orphan reference does not mean evidence is absent."
            )
            st.write(card["orphanRefs"])
        st.write("Lineage families:", card["lineageFamilies"])
        st.write("Limitations:", card["limitations"])
