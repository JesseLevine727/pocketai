#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_CONTROL_BUILD=$(mktemp -d "$ROOT/build/m5_transfer_control.XXXXXX")
verilator --cc --exe --build --assert -Wall --top-module pa_m5_transfer_control \
  --Mdir "$M5_CONTROL_BUILD/obj" -CFLAGS '-std=c++17 -Wall -Wextra -Werror' \
  rtl/m5/pa_m5_transfer_control.sv "$ROOT/tests/m5/transfer_control.cc" \
  >"$M5_CONTROL_BUILD/build.log" 2>&1 || { tail -n 70 "$M5_CONTROL_BUILD/build.log"; exit 1; }
"$M5_CONTROL_BUILD/obj/Vpa_m5_transfer_control" 2>&1 | tee "$M5_CONTROL_BUILD/test.log"
echo "M5 TRANSFER CONTROL EVIDENCE $M5_CONTROL_BUILD"
