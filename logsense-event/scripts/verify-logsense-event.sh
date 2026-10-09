#!/usr/bin/env bash
# Verify the LogSense event deployment: code identity, workspace, real evidence,
# analysis snapshots, control measurement data, no sample case, no secrets.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${LOGSENSE_VENV:-$HOME/venvs/logsense-event}"
export LOGSENSE_WORKSPACE="${LOGSENSE_WORKSPACE:-$HOME/logsense-event-workspace}"
FAIL=0
chk(){ if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; FAIL=1; fi; }

chk "code identity = LogSense 2.0.0rc1" \
  "$VENV/bin/python -c 'import logsense,sys; sys.exit(0 if logsense.__version__==\"2.0.0rc1\" else 1)'"
chk "pinned version doc present" '[ -f "$HERE/code/LOGSENSE_VERSION.txt" ]'
chk "workspace exists" '[ -d "$LOGSENSE_WORKSPACE/cases" ]'

for c in tmf-c16-pass tmf-c16-breach tmf-c7-coverage tmf-s1 tmf-s2-original tmf-s2-retest tmf-s3 tmf-sec02-runaway tmf-enforcement tmf-killswitch; do
  chk "case $c committed" '[ -d "'"$LOGSENSE_WORKSPACE"'/cases/'"$c"'" ]'
done

chk "real audit evidence committed (pass run)" \
  'find "$LOGSENSE_WORKSPACE/cases/tmf-c16-pass" -name "*.jsonl" -o -name "*.txt" | grep -q .'
chk "analysis snapshot exists (c16-breach)" \
  'find "$LOGSENSE_WORKSPACE/cases/tmf-c16-breach" -name "*.json" | grep -q .'
chk "event evidence payload present" '[ -f "$HERE/event-evidence/runs/fault-1791165466-51ab52/audit_records.jsonl" ]'
chk "control measurement snapshots present (c16/c9 bundles)" \
  'find "$HERE/analysis-snapshots" -name "*c16*.json" -o -name "c9-bundle-*.json" | grep -q .'
chk "registry/run-ids/gap-list present" \
  '[ -f "$HERE/event-evidence/register.yaml" ] && [ -f "$HERE/event-evidence/run-ids.txt" ]'
chk "no sample/demo case selected by default" \
  '! "$VENV/bin/python" -c "from logsense.workspace.cases import list_cases;import sys;sys.exit(0 if any(c.case_id.startswith(\"sample\") or \"demo\" in c.case_id for c in list_cases(\"'"$LOGSENSE_WORKSPACE"'\")) else 1)"'
chk "findings present in workspace" \
  'find "$LOGSENSE_WORKSPACE/cases" -type f -name "*.json" -exec grep -l "finding" {} + | head -1 | grep -q .'

# secrets sweep over the bundle
if grep -rInE "(aws_secret_access_key|BEGIN [A-Z ]*PRIVATE KEY|xoxb-|sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16})" "$HERE" >/dev/null 2>&1; then
  echo "FAIL  secrets scan"; FAIL=1
else echo "PASS  secrets scan"; fi

echo; [ $FAIL -eq 0 ] && echo "VERIFY: ALL CHECKS PASSED" || echo "VERIFY: FAILURES ABOVE"
exit $FAIL
