#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source env.sh
OUT="$ROOT/build/pa_sfpu_alu"
mkdir -p "$OUT"
OBJ_DIR="$OUT/obj"
if [[ "${PA_CLEAN:-0}" == 1 ]]; then
  OBJ_DIR="$(mktemp -d "$OUT/obj.clean.XXXXXX")"
fi
verilator --cc --exe --build --assert -Wall --top-module pa_sfpu_alu \
  --Mdir "$OBJ_DIR" -CFLAGS "-std=c++17 -O2" \
  "$ROOT/rtl/sfpu/pa_sfpu_alu.sv" "$ROOT/sim/pa_sfpu/pa_sfpu_alu.cc"
"$OBJ_DIR/Vpa_sfpu_alu"
