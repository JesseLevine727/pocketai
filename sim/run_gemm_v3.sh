#!/usr/bin/env bash
# Qualify the enabled extension AND legacy vectors in the extended hardware.
set -euo pipefail
ulimit -c 0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source env.sh
OUT="$ROOT/build/pa_gemm_v3"
mkdir -p "$OUT"
OBJ_DIR="$OUT/obj"
if [[ "${PA_CLEAN:-0}" == 1 ]]; then
  OBJ_DIR="$(mktemp -d "$OUT/obj.clean.XXXXXX")"
fi
python3 -m unittest tests.m3.test_gemm_v3_ref
python3 -m tests.m3.generate_gemm_vectors "$OUT/vectors.bin"
python3 -m tests.m2.generate_gemm_vectors "$OUT/legacy_vectors.bin"
verilator --cc --exe --build --assert -Wall \
  --top-module pa_gemm "-GEnableWide=1'b1" --Mdir "$OBJ_DIR" \
  -CFLAGS "-std=c++17 -O2 -DPA_GEMM_WIDE_TEST" \
  "$ROOT/rtl/gemm/pa_gemm_slot.sv" "$ROOT/rtl/gemm/pa_gemm.sv" \
  "$ROOT/sim/pa_gemm/pa_gemm.cc"
"$OBJ_DIR/Vpa_gemm" "$OUT/vectors.bin"
"$OBJ_DIR/Vpa_gemm" "$OUT/legacy_vectors.bin"
