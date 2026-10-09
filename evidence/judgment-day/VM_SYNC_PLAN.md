# VM SYNC PLAN — Official C16 Package
Run ONLY when the Workshop IDE/VM becomes reachable. Do NOT execute `submit.sh` at any point in this plan.

## Source (local)
`C:\Users\Subodh Kc\Downloads\kushal handover\handover\package-dryrun-c16\`
- `register.yaml` — frozen-rule mirror (policy 547f4a67, digest sha256:944212e6…, cap 60,000)
- `run-ids.txt`, `gap-list.md`
- `evidence/` (21 files + `evidence/judgment-day/` snapshot)
- `MANIFEST.sha256`, `PACKAGE-DIGEST.txt`

## Steps on the VM
```bash
# 1) Stage evidence
mkdir -p ~/evidence
cp -r package-dryrun-c16/evidence/* ~/evidence/

# 2) Top-level required files
cp package-dryrun-c16/register.yaml ~/register.yaml
cp package-dryrun-c16/gap-list.md   ~/gap-list.md
cp package-dryrun-c16/run-ids.txt   ~/run-ids.txt

# 3) Optional judgment-day snapshot
mkdir -p ~/evidence/judgment-day
cp -r package-dryrun-c16/evidence/judgment-day/* ~/evidence/judgment-day/

# 4) Verify integrity after copy
cd ~/evidence && sha256sum -c <(grep -v 'judgment-day' ../package-dryrun-c16/MANIFEST.sha256) || \
  (cd ~/evidence && sha256sum -c ../package-dryrun-c16/MANIFEST.sha256)

# 5) Validate package presence (no submission)
test -f ~/register.yaml && test -f ~/gap-list.md && test -f ~/run-ids.txt && \
  test -d ~/evidence && test -f ~/starter/submit.sh && echo "PACKAGE READY"

# 6) STOP — do NOT run ~/starter/submit.sh
```

## Rules
- `submit.sh` remains UNEXECUTED; submission is a facilitator/judge action.
- No secrets are part of the package; runtime tokens stay off-VM/out of evidence.
- Verify MANIFEST.sha256 before declaring synced; report digest drift, never fix silently.
