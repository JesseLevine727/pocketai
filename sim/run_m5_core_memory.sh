#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_CORE_MEMORY_BUILD=$(mktemp -d "$ROOT/build/m5_core_memory.XXXXXX")
# This toolchain can split a timed fork into a generated C++ coroutine with no
# return. Keep the test coroutine intact; make that compiler diagnostic fatal.
verilator --binary --timing --assert -Wall --output-split 0 --output-split-cfuncs 0 \
  -CFLAGS '-Werror=return-type' --top-module pa_m5_core_memory_tb \
  --Mdir "$M5_CORE_MEMORY_BUILD" rtl/m5/pa_m5_obi_router.sv rtl/m5/pa_m5_obi_ddr.sv \
  rtl/m5/pa_m5_memory_arbiter.sv tests/m5/pa_m5_core_memory_tb.sv \
  >"$M5_CORE_MEMORY_BUILD/build.log" 2>&1 || { tail -n 80 "$M5_CORE_MEMORY_BUILD/build.log"; exit 1; }
"$M5_CORE_MEMORY_BUILD/Vpa_m5_core_memory_tb" "$@" | tee "$M5_CORE_MEMORY_BUILD/test.log"
echo "M5 CORE MEMORY EVIDENCE $M5_CORE_MEMORY_BUILD"
