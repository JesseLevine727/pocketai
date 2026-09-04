#!/usr/bin/env bash
# Generate authoritative M2 vectors, build the standalone RTL, and compare all
# output words under deterministic input/output stalls.
set -euo pipefail
ulimit -c 0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

OUT="build/pa_gemm"
VECTORS="build/m2/gemm_vectors.bin"
mkdir -p "$OUT" "$(dirname "$VECTORS")"
OBJ_DIR="$OUT/obj"
if [[ "${PA_CLEAN:-0}" == "1" ]]; then
  OBJ_DIR="$(mktemp -d "$OUT/obj.clean.XXXXXX")"
fi

python3 -m unittest tests.m2.test_gemm_ref
python3 tests/m2/generate_gemm_vectors.py "$VECTORS"

verilator --cc --exe --build --assert -Wall \
  --top-module pa_gemm \
  --Mdir "$OBJ_DIR" \
  -CFLAGS "-std=c++17 -O2" \
  "$ROOT/rtl/gemm/pa_gemm_slot.sv" "$ROOT/rtl/gemm/pa_gemm.sv" \
  "$ROOT/sim/pa_gemm/pa_gemm.cc"

"$OBJ_DIR/Vpa_gemm" "$VECTORS"
