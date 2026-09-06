#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_MEMORY_BUILD=$(mktemp -d "$ROOT/build/m5_memory_bridge.XXXXXX")
verilator --binary --timing --assert -Wall --top-module pa_m5_memory_bridge_tb \
  --Mdir "$M5_MEMORY_BUILD" rtl/m5/pa_m5_page_translate.sv rtl/m5/pa_m5_axi_burst.sv \
  rtl/m5/pa_m5_memory_bridge.sv tests/m5/pa_m5_memory_bridge_tb.sv \
  >"$M5_MEMORY_BUILD/build.log" 2>&1 || { tail -n 80 "$M5_MEMORY_BUILD/build.log"; exit 1; }
"$M5_MEMORY_BUILD/Vpa_m5_memory_bridge_tb" | tee "$M5_MEMORY_BUILD/test.log"
echo "M5 MEMORY BRIDGE EVIDENCE $M5_MEMORY_BUILD"
