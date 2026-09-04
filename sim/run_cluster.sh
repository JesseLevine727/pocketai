#!/usr/bin/env bash
# PocketAI-T M1b cluster test: build the firmware, build the Verilator sim
# via FuseSoC, run it, and check the results.
#
# PASS = AXI data/strobe/error checks pass, both harts publish the expected CPU
# workload checksums, 10,000 interrupt-driven mailbox exchanges and message
# checksums match, the UART readiness lines are present, and the sim exits 0.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

CT="sim/cluster_test"
OUT="build/pa_cluster"
SIMDIR="build/pocketai_pa_pa_cluster_0.1/sim-verilator"
SIM="$SIMDIR/Vpa_cluster_top"
LOG="$SIMDIR/pa_cluster.log"

# 1. Build the cluster firmware (one ELF for both harts, LMA 0x0).
bash scripts/build_m1_firmware.sh

# 2. Build/update the Verilator sim through FuseSoC.  Do not guard this with
# an executable-exists check: that can silently run stale RTL after edits.
clean_args=()
if [[ "${PA_CLEAN:-0}" == "1" ]]; then
  clean_args+=(--clean)
fi
echo "[run_cluster] building Verilator sim via FuseSoC ..."
fusesoc --cores-root=sim/pa_cluster --cores-root=rtl/soc \
  --cores-root=rtl/ibex-orig \
  run --target=sim "${clean_args[@]}" --build pocketai:pa:pa_cluster

if [[ ! -x "$SIM" ]]; then
  echo "[run_cluster] FAIL: simulator was not produced: $SIM" >&2
  exit 1
fi

# 3. Run the sim, loading the ELF into RAM (registered as "ram" @0x0).
#    Run from the sim dir so the UART log (pa_cluster.log) lands there.
echo "[run_cluster] running simulation ..."
rm -f "$LOG" "$OUT/sim.out"
set +e
(cd "$SIMDIR" && ./Vpa_cluster_top --meminit="ram,$ROOT/$OUT/cluster.elf" \
  >"$ROOT/$OUT/sim.out" 2>&1)
sim_rc=$?
set -e

echo "[run_cluster] sim stdout (exit=$sim_rc):"
cat "$OUT/sim.out"
echo "=== UART capture (pa_cluster.log) ==="
cat "$LOG"

ok=1
if [ "$sim_rc" -ne 0 ]; then
  echo "[run_cluster] FAIL: sim exited $sim_rc"
  ok=0
fi
if ! grep -q "H0 READY" "$LOG"; then
  echo "[run_cluster] FAIL: 'H0 READY' missing from UART log"
  ok=0
fi
if ! grep -q "H1 READY" "$LOG"; then
  echo "[run_cluster] FAIL: 'H1 READY' missing from UART log"
  ok=0
fi
if ! grep -q "AXI OK" "$OUT/sim.out"; then
  echo "[run_cluster] FAIL: 'AXI OK' missing from sim stdout"
  ok=0
fi
if ! grep -q "M1 RESULTS OK" "$OUT/sim.out"; then
  echo "[run_cluster] FAIL: 'M1 RESULTS OK' missing from sim stdout"
  ok=0
fi

if [ "$ok" -eq 1 ]; then
  echo "[run_cluster] PASS"
else
  exit 1
fi
