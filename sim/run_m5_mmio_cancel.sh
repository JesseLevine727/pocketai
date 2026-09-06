#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_CANCEL_BUILD=$(mktemp -d "$ROOT/build/m5_mmio_cancel.XXXXXX")
verilator --cc --exe --build --assert -Wall --top-module pa_m5_mmio_cancel \
  --Mdir "$M5_CANCEL_BUILD/obj" -CFLAGS '-std=c++17 -Wall -Wextra -Werror' \
  rtl/m5/pa_m5_mmio_cancel.sv "$ROOT/tests/m5/mmio_cancel.cc" \
  >"$M5_CANCEL_BUILD/build.log" 2>&1 || { tail -n 70 "$M5_CANCEL_BUILD/build.log"; exit 1; }
"$M5_CANCEL_BUILD/obj/Vpa_m5_mmio_cancel" 2>&1 | tee "$M5_CANCEL_BUILD/test.log"
echo "M5 MMIO CANCEL EVIDENCE $M5_CANCEL_BUILD"
