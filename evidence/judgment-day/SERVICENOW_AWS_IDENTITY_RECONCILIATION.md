# ServiceNow AICT ↔ AWS Identity Reconciliation — TM Forum Event

**Status: `ASSUMEROLE_PROVEN` — DISCOVERY_PENDING** — verified in the
Workshop IDE (ec2-user session, `a-02-code-editor-IdeInstanceRole`).

**Verified evidence (CloudTrail, account 352826992186):**
- `aws sts get-caller-identity` → `Account: 352826992186`, caller
  `arn:aws:sts::352826992186:assumed-role/a-02-code-editor-IdeInstanceRole-TOk7di7HLtmH/i-0c6d1ad39042a2839`
- `aws iam get-role SgcAictReadOnlyAccessRole` → ARN
  `arn:aws:iam::352826992186:role/SgcAictReadOnlyAccessRole`, created
  `2026-10-04T22:03:10Z`; trust: `Effect: Allow`,
  `Principal: arn:aws:iam::352826992186:user/ServiceNowAictUser`,
  `Action: sts:AssumeRole`
- CloudTrail `lookup-events` (EventName=AssumeRole, roleArn filter):
  **5 events** — `caller=ServiceNowAictUser`,
  `role=SgcAictReadOnlyAccessRole`, `session=352826992186-session`
- Note: `lookup-events` on `AttributeKey=ResourceName` returned empty —
  ResourceName does not index the AssumeRole roleArn; the EventName +
  roleArn filter is the correct query. **eventTime not yet captured** — see
  refinement command below.

## A. Verification protocol (run in Workshop IDE with fresh creds)

### A.1 Connector operation — progression: CONFIGURED → ACTIVE → ASSUMEROLE_OBSERVED → DISCOVERY_OBSERVED

```bash
# 1. Confirm identity (must be account 352826992186)
aws sts get-caller-identity

# 2. Does the read-only role exist + trust policy intact?
aws iam get-role --role-name SgcAictReadOnlyAccessRole \
  --query 'Role.[Arn,CreateDate,AssumeRolePolicyDocument]'

# 3. CloudTrail: who has assumed it? (external principal = connector proof)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=SgcAictReadOnlyAccessRole \
  --start-time <RESOLUTION_REPORT_TIME> --max-results 50 \
  --query 'Events[].{t:EventTime,e:EventName,u:Username,ip:SourceIPAddress,ua:CloudTrailEvent}'

# 4. Filter for non-AWS-service principals
#    (exclude bedrock-agentcore/eks-nodegroup internals seen before —
#     looking for servicenow.com userAgent or external assumed-role principal)
```

**Classification rule:** `SERVICENOW_ASSUME_ROLE = OBSERVED` only if a
CloudTrail `AssumeRole` event on `SgcAictReadOnlyAccessRole` carries a
non-AWS-service principal/UA consistent with ServiceNow. Role existence alone
≠ connector use.

### A.2 AICT discovery output (requires facilitator/instance access)

Ask facilitator OR use participant-accessible AICT surface. For each item
record `DISCOVERED / PARTIAL / NOT_DISCOVERED / NOT_EXPOSED / UNKNOWN` +
native `sys_id`/asset ID (never display-name alone):

| Item | State | sys_id / native ID |
|---|---|---|
| Customer Agent (`customer-experience-agent`) | UNKNOWN | |
| IT Agent | UNKNOWN | |
| Network Agent (`network-resolution`… ) | UNKNOWN | |
| AgentCore runtime | UNKNOWN | |
| AgentCore endpoint | UNKNOWN | |
| AWS account/resource (352826992186) | UNKNOWN | |
| model identity | UNKNOWN | |
| tool identity | UNKNOWN | |
| prompt/config · execution plan · task execution | UNKNOWN | |
| session · trace · evaluation | UNKNOWN | |
| CloudWatch/log source | UNKNOWN | |

### A.3 Match rules (map to `matchAwsToAict` semantics)

`MATCHED_NATIVE_ID` = same stable ID both sides (ARN/native id on the AICT
record) · `MATCHED_CORROBORATED` = native id + corroborating attribute ·
`PROVISIONAL_NAME_MATCH` = names equal only · `UNMATCHED` / `CONFLICT` /
`UNKNOWN`. **Never promote PROVISIONAL_NAME_MATCH on name equality alone.**

## B. Reconciliation table (fill after A.1–A.2)

| SERVICENOW_NAME | sys_id | NATIVE_ID | AWS_NAME | AWS_ARN | MATCH_STATE | MATCH_BASIS |
|---|---|---|---|---|---|---|
| PENDING | | | customer-experience-agent | | UNKNOWN | |
| PENDING | | | (IT agent) | | UNKNOWN | |
| PENDING | | | network-resolution… | | UNKNOWN | |
| PENDING | | | agentgateway listener `llm` | | UNKNOWN | |

## C. SEC-07 state

- `SEC07_PREVIOUS_STATE` = AWS_PRECHECK_COMPLETE + FACILITATOR_ACTIVATION_PENDING
  (0 observed external AssumeRole — all CloudTrail AssumeRole since 05:00Z were
  internal AWS service identities)
- `SEC07_CURRENT_STATE` = **ASSUMEROLE_PROVEN** — 5 CloudTrail AssumeRole
  events by `ServiceNowAictUser` on `SgcAictReadOnlyAccessRole`
  (`352826992186-session`) observed post-resolution
- `SEC07_FACILITATOR_DEPENDENCY_STATE` = RESOLVED_PENDING_DISCOVERY (connector
  is operating; facilitator blocker closes once A.2 discovery confirmed)
- `SEC07_DISCOVERY_STATE` = UNKNOWN — AICT inventory not yet inspected
- `SEC07_CROSS_PLATFORM_IDENTITY_STATE` = UNKNOWN — no sys_ids captured yet
- `SEC07_CLOSED` = **PARTIAL** — closes fully only with DISCOVERY_OBSERVED;
  cross-platform identity may remain PARTIAL without reopening the facilitator
  blocker

**Follow-up command (capture eventTime + one raw event for the bundle):**

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --max-results 50 --query 'Events[].CloudTrailEvent' --output json \
  | python3 -c "
import sys, json
for evt in json.load(sys.stdin):
    p = json.loads(evt)
    if 'SgcAict' in p.get('requestParameters',{}).get('roleArn',''):
        print(p['eventTime'], p['eventID'],
              p['userIdentity'].get('userName'),
              p.get('sourceIPAddress'), p.get('userAgent','')[:60])
"
```

## D. HAIEC capability inventory (existing — no new connector built)

| Capability | State | Evidence/owner |
|---|---|---|
| ServiceNow integration contract + client | IMPLEMENTED | `lib/integrations/servicenow/` (client, contract, normalize, preflight, pull — `servicenow-integration-1.0.0`) |
| AICT asset normalization → STATE_OBSERVATION evidence | IMPLEMENTED | `servicenow/normalize.ts` (`AICT_ASSET_TARGET_MAP`; inventory ≠ runtime action) |
| Capability preflight probes (Table API, Agent Studio `sn_aia_agent`, execution plans/tasks, `sn_aia_usecase`) | IMPLEMENTED | `SERVICENOW_DEFAULT_PROBES`; `aiAssetsInventoryApi`/`mcpInventory` are OPERATOR-declared probes only |
| AWS AgentCore discovery | IMPLEMENTED | `lib/integrations/aws/discovery.ts` |
| AWS↔AICT deterministic identity matching | IMPLEMENTED | `lib/integrations/aws/identity-match.ts` — `matchAwsToAict`, states MATCHED/PROVISIONAL_NAME_MATCH/AMBIGUOUS/MISMATCHED/NOT_ESTABLISHED; READY only if ≥1 MATCHED |
| Cross-platform inventory projection | IMPLEMENTED | `AictAwsIntegrationState`: CONNECTED→AGENTS_DISCOVERED→READY/LIMITED |
| Human governance channel | PROVEN via email/webhook (synthetic test); ServiceNow incident path PENDING | `monitoring-chain/` receipts |
| EVENT_BINDING_STATE | NOT_BOUND — no live AICT records ingested yet | |
| JUDGE_VALUE | Strong IF observed: cross-platform discovery + identity continuity = genuine enterprise-governance corroboration | |

## E. Five-plane impact (legitimate, non-forced)

| PLANE | NEW_SERVICENOW_EVIDENCE | STATE_CHANGE | LIMITATION |
|---|---|---|---|
| OBSERVED | CloudTrail external AssumeRole on `SgcAictReadOnlyAccessRole` | NOT_OBSERVED→OBSERVED **if** A.1 finds it | proves connector operation, not asset correctness |
| OBSERVED | AICT discovery rows for event assets | strengthen inventory/governance corroboration | `AICT_INVENTORY != OBSERVED_RUNTIME_ACTION` — discovery rows are state observations, never runtime proof |
| POLICY_AUTHORIZED | role trust policy already provisioned | unchanged | already documented |
| EFFECTIVELY_GRANTED / CODE_CAPABLE / REQUESTED | — | none | no new evidence these planes |

## F. Human-governance path (separate from AICT discovery)

Participant-accessible ServiceNow write surface: **UNKNOWN** — connector
activation ≠ incident rights. Verify on the instance:
`INCIDENT_API_AVAILABLE` / `ALERT_API_AVAILABLE` / `ASSIGNABLE_QUEUE` /
`NAMED_HUMAN_RECIPIENT` / `ACKNOWLEDGEMENT` / `STATUS_TRANSITION` /
`NATIVE_INCIDENT_SYS_ID` — probe `/api/now/table/incident` write permission
with a labeled TEST record only if authorized; otherwise UNKNOWN.

## G. Do not blur

- `CONFIGURED ≠ ACTIVE ≠ ASSUMEROLE_OBSERVED ≠ DISCOVERY_OBSERVED`
- `AICT discovery ≠ runtime enforcement evidence`
- `connector resolved ≠ incident/human-loop path available`
- If discovery proves but identity matching stays partial → SEC-07 =
  `PARTIAL`, never closed on names alone.
