# ARTIFACT 5 — ONE-PAGE ARCHITECTURE
**DEVIN EVENT-DAY WORKING MIRROR — Drive copy remains canonical.**

```
        AWS / AgentCore / agentgateway (modaas-agw)
        ┌───────────────────────────┐   ┌──────────────────────────┐
        │ CloudWatch native records │   │ native records (offline) │
        └─────────────┬─────────────┘   └────────────┬─────────────┘
                      │                              │
        participant-owned live forwarder             LogSense (adapter)
        handover/live_forwarder.py                   deterministic normalize + measure
        cursor + native-id dedupe + strip            │
                      │                              │
        HAIEC OTLP binder 52ec5f04 ──────► HAIEC EVIDENCE ◄───────
        (evidence:ingest token; mirrored,  │
         provenance-labeled)               │
                                           ▼
                              HAIEC CONTROL TEST
                    owns the deterministic ALLOW/PASS/BREACH
```

- Telemetry never judges. LogSense never creates a verdict. HAIEC Control Test owns the final deterministic result.
- Platform-owned collector mutation = RESTRICTED (protected namespaces); participant-owned forwarding = PROVEN.
- Runtime decisions (Cedar/gateway PDP) ≠ post-run assurance results — kept distinct everywhere.
