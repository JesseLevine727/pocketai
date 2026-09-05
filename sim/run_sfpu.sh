#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source env.sh
OUT="$ROOT/build/pa_sfpu"
mkdir -p "$OUT"
OBJ_DIR="$OUT/obj"
if [[ "${PA_CLEAN:-0}" == 1 ]]; then
  OBJ_DIR="$(mktemp -d "$OUT/obj.clean.XXXXXX")"
fi
python3 -m tests.m3.generate_sfpu_tables "$ROOT/rtl/sfpu" --check
python3 -m tests.m3.generate_sfpu_tables "$OUT"
python3 -m tests.m3.generate_sfpu_vectors "$OUT/vectors.bin"
verilator --cc --exe --build --assert -Wall --public-flat-rw \
  --top-module pa_sfpu --Mdir "$OBJ_DIR" -CFLAGS "-std=c++17 -O2" \
  "$ROOT/rtl/sfpu/pa_sfpu_alu.sv" "$ROOT/rtl/sfpu/pa_sfpu_compute.sv" \
  "$ROOT/rtl/sfpu/pa_sfpu.sv" "$ROOT/sim/pa_sfpu/pa_sfpu.cc"
cd "$OUT"
"$OBJ_DIR/Vpa_sfpu" "$OUT/vectors.bin"
