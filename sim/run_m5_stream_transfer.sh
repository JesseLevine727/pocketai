#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_STREAM_BUILD=$(mktemp -d "$ROOT/build/m5_stream_transfer.XXXXXX")
verilator --cc --exe --build --assert -Wall --top-module pa_m5_stream_transfer \
  --Mdir "$M5_STREAM_BUILD/obj" -CFLAGS '-std=c++17 -Wall -Wextra -Werror' \
  rtl/m5/pa_m5_stream_transfer.sv "$ROOT/tests/m5/stream_transfer.cc" \
  >"$M5_STREAM_BUILD/build.log" 2>&1 || { tail -n 70 "$M5_STREAM_BUILD/build.log"; exit 1; }
"$M5_STREAM_BUILD/obj/Vpa_m5_stream_transfer" 2>&1 | tee "$M5_STREAM_BUILD/test.log"
echo "M5 STREAM EVIDENCE $M5_STREAM_BUILD"
