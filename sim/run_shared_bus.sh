#!/usr/bin/env bash
# Shared-bus protocol regression, including req held high between transfers.
set -euo pipefail
ulimit -c 0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

OUT="build/pa_shared_bus"
mkdir -p "$OUT"

verilator --binary --timing -Wall -Wno-TIMESCALEMOD \
  --top-module pa_shared_bus_tb \
  --Mdir "$OUT/obj" \
  -o Vpa_shared_bus_tb \
  rtl/soc/pa_shared_bus.sv sim/pa_shared_bus/pa_shared_bus_tb.sv

"$OUT/obj/Vpa_shared_bus_tb"
