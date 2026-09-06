#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_AXI_BUILD=$(mktemp -d "$ROOT/build/m5_axi_burst.XXXXXX")
verilator --binary --timing --assert -Wall --top-module pa_m5_axi_burst_tb \
  --Mdir "$M5_AXI_BUILD" rtl/m5/pa_m5_axi_burst.sv tests/m5/pa_m5_axi_burst_tb.sv \
  >"$M5_AXI_BUILD/build.log" 2>&1 || { tail -n 80 "$M5_AXI_BUILD/build.log"; exit 1; }
"$M5_AXI_BUILD/Vpa_m5_axi_burst_tb" | tee "$M5_AXI_BUILD/test.log"
echo "M5 AXI BURST EVIDENCE $M5_AXI_BUILD"
