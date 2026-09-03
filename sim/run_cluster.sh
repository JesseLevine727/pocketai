#!/usr/bin/env bash
# PocketAI-T M1b cluster test: build the firmware, build the Verilator sim
# via FuseSoC, run it, and check the results.
#
# PASS = the sim prints "AXI OK" (AXI4-Lite self-test run before the cores
# are released from reset), the UART capture (pa_cluster.log) contains
# "P0" and "P1: PONG OK", and the sim exits 0 (firmware halted the sim).
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

mkdir -p "$OUT"

# 1. Build the cluster firmware (one ELF for both harts, LMA 0x0).
riscv32-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -nostdlib -ffreestanding \
  -T "$CT/link.ld" "$CT/crt0.S" "$CT/main.c" -o "$OUT/cluster.elf"
echo "[run_cluster] cluster.elf built: $OUT/cluster.elf"

# 2. Build the Verilator sim through FuseSoC (cached on disk once built).
if [ ! -x "$SIM" ]; then
  echo "[run_cluster] building Verilator sim via FuseSoC ..."
  fusesoc --cores-root=. --cores-root=rtl/ibex-orig \
    run --target=sim --build pocketai:pa:pa_cluster
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
if ! grep -q "P0" "$LOG"; then
  echo "[run_cluster] FAIL: 'P0' missing from UART log"
  ok=0
fi
if ! grep -q "P1: PONG OK" "$LOG"; then
  echo "[run_cluster] FAIL: 'P1: PONG OK' missing from UART log"
  ok=0
fi
if ! grep -q "AXI OK" "$OUT/sim.out"; then
  echo "[run_cluster] FAIL: 'AXI OK' missing from sim stdout"
  ok=0
fi

if [ "$ok" -eq 1 ]; then
  echo "[run_cluster] PASS"
else
  exit 1
fi
