#!/usr/bin/env bash
# Short production-firmware/header check; deliberately incomplete data mapping.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
if [[ $# != 2 ]]; then
  echo "usage: bash sim/run_m5_startup.sh firmware.bin model.bin" >&2; exit 1
fi
M5_STARTUP_FIRMWARE=$(realpath "$1")
M5_STARTUP_MODEL=$(realpath "$2")
source env.sh
M5_STARTUP_BUILD=$(mktemp -d "$ROOT/build/m5_startup.XXXXXX")
fusesoc --cores-root=sim/pa_m5_cluster --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim --work-root="$M5_STARTUP_BUILD/sim" --build pocketai:pa:pa_m5_accelerators \
  >"$M5_STARTUP_BUILD/build.log" 2>&1 || { tail -n 60 "$M5_STARTUP_BUILD/build.log"; exit 1; }
python3 scripts/check_m5_sources.py "$M5_STARTUP_BUILD/sim"
for m5_delay in 0 64 256; do
  (cd "$M5_STARTUP_BUILD/sim" && PA_M5_AXI_DELAY=$m5_delay \
    ./Vpa_m5_cluster_top "$M5_STARTUP_FIRMWARE" "$M5_STARTUP_MODEL") \
    2>&1 | tee "$M5_STARTUP_BUILD/delay_$m5_delay.log"
done
echo "M5 PRODUCTION STARTUP EVIDENCE $M5_STARTUP_BUILD"
