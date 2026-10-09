from __future__ import annotations


def validate_canonical_event_semantics(event: dict) -> list[str]:
    errors=[]
    if event.get('timeQuality') == 'MISSING' and event.get('eventTime') is not None:
        errors.append('MISSING_TIME_MUST_NOT_HAVE_EVENT_TIME')
    if event.get('eventClassAssignment') == 'PROPOSED' and not event.get('limitations'):
        errors.append('PROPOSED_EVENT_CLASS_REQUIRES_LIMITATION')
    if event.get('orderingBasis') == 'EVENT_TIME' and event.get('eventTime') is None:
        errors.append('EVENT_TIME_ORDERING_REQUIRES_EVENT_TIME')
    return errors

def validate_cause_candidate_semantics(cause: dict) -> list[str]:
    errors=[]
    if cause.get('canonical') is not False:
        errors.append('CAUSE_CANDIDATE_MUST_BE_NON_CANONICAL')
    if cause.get('generatedBy') == 'AI_HYPOTHESIS' and cause.get('establishmentState') in {'ESTABLISHED','CORROBORATED'}:
        errors.append('AI_HYPOTHESIS_CANNOT_ESTABLISH_CAUSE_ALONE')
    if cause.get('establishmentState') == 'CORROBORATED' and len(set(cause.get('independentLineageFamilies',[]))) < 2:
        errors.append('CORROBORATED_REQUIRES_INDEPENDENT_LINEAGES')
    return errors


def validate_comparison_compatibility_semantics(comp: dict) -> list[str]:
    errors=[]
    states=[d.get('state') for d in comp.get('dimensions',[])]
    elig=comp.get('driftComparisonEligibility')
    if 'INCOMPATIBLE' in states and elig != 'INELIGIBLE':
        errors.append('INCOMPATIBLE_DIMENSION_REQUIRES_INELIGIBLE_COMPARISON')
    if elig == 'ELIGIBLE' and any(s not in {'EXACT','COMPATIBLE'} for s in states):
        errors.append('ELIGIBLE_REQUIRES_ALL_DIMENSIONS_COMPARABLE')
    if comp.get('overallState') == 'EXACT' and any(s != 'EXACT' for s in states):
        errors.append('EXACT_OVERALL_REQUIRES_ALL_DIMENSIONS_EXACT')
    return errors

def validate_delta_fact_semantics(delta: dict) -> list[str]:
    errors=[]
    if delta.get('kind') == 'REMOVED_FROM_OBSERVED_SET' and delta.get('absenceEstablished') and not delta.get('completenessEvidenceRefs'):
        errors.append('PROVEN_ABSENCE_REQUIRES_COMPLETENESS_EVIDENCE')
    if delta.get('kind') == 'INCOMPARABLE' and not delta.get('limitations'):
        errors.append('INCOMPARABLE_DELTA_REQUIRES_LIMITATION')
    return errors

def validate_scenario_sequence_semantics(seq: dict) -> list[str]:
    errors=[]
    states=seq.get('states',[])
    nums=[x.get('scenarioSequence') for x in states]
    levels=[x.get('scenarioLevel') for x in states]
    sets=[x.get('evidenceSetId') for x in states]
    if len(nums) != len(set(nums)):
        errors.append('SCENARIO_SEQUENCE_VALUES_MUST_BE_UNIQUE')
    if len(levels) != len(set(levels)):
        errors.append('SCENARIO_LEVELS_MUST_BE_UNIQUE')
    if len(sets) != len(set(sets)):
        errors.append('SCENARIO_EVIDENCE_SETS_MUST_BE_UNIQUE')
    return errors

def validate_coverage_semantics(cov: dict) -> list[str]:
    errors=[]
    for name,cell in cov.items():
        if not isinstance(cell,dict) or 'state' not in cell:
            continue
        if cell.get('state') == 'MISSING' and not cell.get('gapRefs'):
            errors.append(f'{name.upper()}_MISSING_REQUIRES_GAP_REF')
        if cell.get('state') == 'PRESENT' and not cell.get('evidenceRefs'):
            errors.append(f'{name.upper()}_PRESENT_REQUIRES_EVIDENCE_REF')
    return errors


def validate_cause_rule_semantics(rule: dict) -> list[str]:
    errors=[]
    req=rule.get('requiredPredicates',[])
    non_signal=[p for p in req if p.get('kind') != 'DETECTION_SIGNAL']
    pol=rule.get('establishmentPolicy',{})
    if pol.get('allowEstablished') and not non_signal:
        errors.append('ESTABLISHABLE_RULE_REQUIRES_NON_SIGNAL_PREDICATE')
    if rule.get('ruleClass') == 'EVIDENCE_LIMITATION' and rule.get('defaultCauseRole') == 'ROOT_MECHANISM':
        errors.append('EVIDENCE_LIMITATION_CANNOT_DEFAULT_TO_ROOT_MECHANISM')
    ids=[p.get('predicateId') for p in req + rule.get('anyOfPredicates',[]) + rule.get('forbiddenPredicates',[]) + rule.get('corroborators',[])]
    if len(ids) != len(set(ids)):
        errors.append('PREDICATE_IDS_MUST_BE_UNIQUE_WITHIN_RULE')
    return errors

def validate_cause_evaluation_semantics(evaluation: dict, rule_by_id: dict[str,dict]) -> list[str]:
    errors=[]
    rule=rule_by_id.get(evaluation.get('ruleId') or "")
    if not rule:
        return ['UNKNOWN_CAUSE_RULE']
    results={x.get('predicateId'):x.get('state') for x in evaluation.get('predicateResults',[])}
    req=[x['predicateId'] for x in rule.get('requiredPredicates',[])]
    missing=[pid for pid in req if results.get(pid) != 'SATISFIED']
    state=evaluation.get('resultState')
    if state in {'ESTABLISHED','CORROBORATED'} and missing:
        errors.append('ESTABLISHED_CAUSE_REQUIRES_ALL_REQUIRED_PREDICATES')
    if state in {'ESTABLISHED','CORROBORATED'}:
        non_signal=[p for p in rule.get('requiredPredicates',[]) if p.get('kind') != 'DETECTION_SIGNAL' and results.get(p.get('predicateId')) == 'SATISFIED']
        if not non_signal:
            errors.append('DETECTION_SIGNAL_ALONE_CANNOT_ESTABLISH_CAUSE')
    if state == 'CORROBORATED':
        fams=set(evaluation.get('candidate',{}).get('independentLineageFamilies',[]))
        if len(fams) < rule.get('establishmentPolicy',{}).get('corroboratedIndependentLineages',2):
            errors.append('CORROBORATED_REQUIRES_RULE_MINIMUM_INDEPENDENT_LINEAGES')
    if rule.get('establishmentPolicy',{}).get('allowEstablished') is False and state in {'ESTABLISHED','CORROBORATED'}:
        errors.append('RULE_DOES_NOT_ALLOW_ESTABLISHED_STATE')
    return errors


def validate_relation_evaluation_semantics(evaluation: dict, entry_by_type: dict[str,dict]) -> list[str]:
    errors=[]
    entry=entry_by_type.get(evaluation.get('relationType') or "")
    if not entry:
        return ['UNKNOWN_RELATION_TYPE']
    decision=evaluation.get('decision')
    basis=evaluation.get('admissionBasis')
    ceiling=entry.get('admissionCeiling')
    if decision=='ESTABLISHED':
        if ceiling in {'PARTIAL','PROPOSED_ONLY','BLOCKED'}:
            errors.append('DECISION_EXCEEDS_ADMISSION_CEILING')
        if basis not in entry.get('establishmentEvidenceBases',[]):
            errors.append('ESTABLISHED_BASIS_NOT_ALLOWED')
        if not evaluation.get('evidenceRefs'):
            errors.append('ESTABLISHED_RELATION_REQUIRES_EVIDENCE')
        req=set(entry.get('requiredConditions',[]))
        sat=set(evaluation.get('satisfiedConditions',[]))
        if not req.issubset(sat):
            errors.append('ESTABLISHED_RELATION_MISSING_REQUIRED_CONDITIONS')
        if entry.get('requiresIndependentLineageForEstablishment') and len(set(evaluation.get('lineageFamilies',[])))<2:
            errors.append('ESTABLISHED_RELATION_REQUIRES_INDEPENDENT_LINEAGE')
    if decision=='PARTIAL' and ceiling=='PROPOSED_ONLY':
        errors.append('PARTIAL_EXCEEDS_ADMISSION_CEILING')
    if basis in entry.get('forbiddenAdmissionBases',[]):
        errors.append('FORBIDDEN_RELATION_ADMISSION_BASIS')
    # identity threshold: EXACT entries cannot establish on weaker identity
    if decision=='ESTABLISHED':
        if entry.get('requiredSourceIdentityState')=='EXACT' and evaluation.get('sourceIdentityState')!='EXACT':
            errors.append('SOURCE_IDENTITY_NOT_EXACT')
        if entry.get('requiredTargetIdentityState')=='EXACT' and evaluation.get('targetIdentityState')!='EXACT':
            errors.append('TARGET_IDENTITY_NOT_EXACT')
    if decision=='CONTRADICTED' and len(set(evaluation.get('evidenceRefs',[]))) < entry.get('contradictionMinimumEvidenceRefs',2):
        errors.append('CONTRADICTED_RELATION_REQUIRES_COMPETING_EVIDENCE')
    return errors


def validate_action_group_semantics(group: dict) -> list[str]:
    errors=[]
    ident=group.get('actionIdentity',{})
    if group.get('establishmentState')=='ESTABLISHED':
        if ident.get('identityState')!='EXACT':
            errors.append('ESTABLISHED_ACTION_GROUP_REQUIRES_EXACT_IDENTITY')
        if not ident.get('actorRef') or not (ident.get('nativeOperation') or ident.get('canonicalOperation')) or not (ident.get('targetRef') or ident.get('resourceScope')):
            errors.append('ESTABLISHED_ACTION_GROUP_REQUIRES_ACTOR_OPERATION_TARGET_SCOPE')
        weak=set(ident.get('identityBasis',[])) & {'TRACE_ID_ONLY','TIMESTAMP_PROXIMITY','SAME_ACTOR_TARGET_ONLY'}
        if weak:
            errors.append('WEAK_CORRELATION_CANNOT_ESTABLISH_ACTION_GROUP')
    return errors

def validate_source_qualification_semantics(result: dict, profile_by_id: dict[str,dict]) -> list[str]:
    errors=[]
    p=profile_by_id.get(result.get('profileId') or "")
    if not p:
        return ['UNKNOWN_SOURCE_QUALIFICATION_PROFILE']
    claim=result.get('claimClass')
    decision=result.get('decision')
    if decision=='CAN_ESTABLISH' and claim not in p.get('canEstablishClaimClasses',[]):
        errors.append('SOURCE_PROFILE_CANNOT_ESTABLISH_CLAIM')
    if decision in {'CAN_ESTABLISH','CAN_SUPPORT'} and claim in p.get('cannotEstablishClaimClasses',[]):
        errors.append('SOURCE_PROFILE_EXPLICITLY_FORBIDS_CLAIM')
    if p.get('requiresExactSubjectBinding') and decision=='CAN_ESTABLISH' and result.get('subjectBinding')!='EXACT':
        errors.append('SOURCE_ESTABLISHMENT_REQUIRES_EXACT_SUBJECT_BINDING')
    return errors

def validate_temporal_normalization_semantics(n: dict) -> list[str]:
    errors=[]
    if n.get('state')=='MISSING' and n.get('normalizedEventTime') is not None:
        errors.append('MISSING_TIMESTAMP_CANNOT_BE_FABRICATED')
    if n.get('normalizedEventTime') is not None and not n.get('nativeTimestamp') and n.get('state')!='EXACT':
        errors.append('NORMALIZED_TIME_REQUIRES_NATIVE_TIMESTAMP_OR_EXACT_SOURCE_TIME')
    if n.get('offsetAppliedMs') is not None and not n.get('clockDomainRef'):
        errors.append('CLOCK_OFFSET_REQUIRES_CLOCK_DOMAIN')
    return errors

def validate_relation_catalog_references(matrix: dict, condition_catalog: dict, basis_catalog: dict) -> list[str]:
    errors=[]
    conds={x['conditionId'] for x in condition_catalog.get('conditions',[])}
    bases={x['basisId'] for x in basis_catalog.get('bases',[])}
    for e in matrix.get('entries',[]):
        for c in e.get('requiredConditions',[]):
            if c not in conds:
                errors.append(f"UNKNOWN_RELATION_CONDITION:{e['relationType']}:{c}")
        for k in ['proposalEvidenceBases','establishmentEvidenceBases','forbiddenAdmissionBases']:
            for b in e.get(k,[]):
                if b not in bases:
                    errors.append(f"UNKNOWN_RELATION_BASIS:{e['relationType']}:{b}")
    return errors

def relation_refs_from_rule(rule: dict) -> set[str]:
    out=set(rule.get('relationRefs',[]))
    for grp in ['requiredPredicates','anyOfPredicates','forbiddenPredicates','corroborators']:
        for p in rule.get(grp,[]):
            out.update(p.get('params',{}).get('relationTypes',[]))
    return out
