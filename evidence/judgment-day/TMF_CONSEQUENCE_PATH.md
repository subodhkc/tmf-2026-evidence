# TM Forum — Consequence / Action Path Projection

> WHAT CAN THIS SYSTEM CAUSE? vs WHAT DID THIS RUN ACTUALLY DO? — kept separate.

## Path: customer intent → network consequence

```
Customer intent (scenario)
   | DECLARED + OBSERVED (run manifests, audit)
   v
Customer agent --> governed model/tool boundary
   | AUTHORIZED (Cedar/guardrail decisions) + OBSERVED (gateway calls)
   v
IT agent --> expected NEGOTIATION --> Network agent
   |                ^ MISSING EDGE (0/835 records)
   |                | capability declared != delegation observed
   v                |
network / digital-twin consequence
   DECLARED path only -- OBSERVED edge absent
```

## Edge ledger

| Edge | DECLARED | AUTHORIZED | EFFECTIVELY_GRANTED | CODE_CAPABLE | OBSERVED |
|---|---|---|---|---|---|
| customer intent -> customer agent | yes | yes | yes | yes | yes (audit/OTel) |
| customer/IT agent -> model+tool calls | yes | yes (Cedar ALLOW/DENY) | yes (IAM/key) | yes | yes (gateway 91-call series) |
| IT agent -> NEGOTIATION -> network agent | yes (scenario design) | unproven | unproven | **no** (image lacks A2A primitive) | **NO — the missing edge** |
| agent -> network/digital-twin effect | yes | unproven | unproven | unproven | no direct observation |

## Reading

- The missing NEGOTIATION is not a failed attempt — it is an absent leg of the
  declared consequence path, inside a supplied image with no invocation
  primitive. Root cause investigated; gap OPEN_BUT_DISCLOSED (G-013).
- What the system COULD cause (declared) exceeds what was OBSERVED — that gap
  is exactly the assurance question the exercise demonstrates.
- Do not fabricate the edge; do not extend OBSERVED beyond its evidence.
