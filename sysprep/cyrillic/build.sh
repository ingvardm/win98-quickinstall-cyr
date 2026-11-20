#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build.sh -- one-command reproduction of the two Cyrillic QuickInstall ISOs.
# See README.md / PLAN.md.  Run from anywhere; paths are resolved relative to
# the workspace root (the parent of win98-quickinstall/).
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$HERE/../../.." && pwd)"
TOOL="$HERE/cyrillize.py"
PY="${PYTHON:-python3}"

cd "$WORKSPACE"
echo "Workspace: $WORKSPACE"
echo "Tool:      $TOOL"
echo

# Step 0 (PLAN.md section 6): validate the toolchain and the pure-Python
# CREG registry editor before anything else touches an ISO. No wine needed.
echo "=== Step 0: toolchain / registry-editor smoke test ==="
"$PY" "$TOOL" --smoke-test --iso win98qi_v1.1.0_stock.iso

echo "=== Build 1/2: stock (primary) ==="
"$PY" "$TOOL" --iso win98qi_v1.1.0_stock.iso \
              --out win98qi_v1.1.0_stock_cyr.iso

echo "=== Build 2/2: 98Lite micro / DirectX 8.1 (insert-or-replace) ==="
"$PY" "$TOOL" --iso win98qi_v1.1.0_micro_directx81.iso \
              --out win98qi_v1.1.0_micro_directx81_cyr.iso

echo "=== Verify 1/2: stock ==="
"$PY" "$TOOL" --verify --iso win98qi_v1.1.0_stock_cyr.iso

echo "=== Verify 2/2: 98Lite micro ==="
"$PY" "$TOOL" --verify --iso win98qi_v1.1.0_micro_directx81_cyr.iso

echo
echo "All done. Generated:"
echo "  win98qi_v1.1.0_stock_cyr.iso"
echo "  win98qi_v1.1.0_micro_directx81_cyr.iso"
echo "Source ISOs were never modified; delete the *_cyr.iso files to roll back."
