#!/usr/bin/env bash
# PocketAI-T M1a boot smoke: build the boot program, build the Verilator sim
# via FuseSoC, run it, and print the captured UART output.
#
# PASS = prints "PA M1 BOOT" and exits 0.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

BT="sim/boot_test"
OUT="build/pa_smoke"
SIMDIR="build/pocketai_pa_pa_smoke_0.1/sim-verilator"
SIM="$SIMDIR/Vpa_smoke_top"

mkdir -p "$OUT"

# Refuse to build against an accidental or stale Ibex checkout.
bash scripts/check_deps.sh sim

# 1. Build the boot program (ELF, LMA 0x0).
riscv32-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -nostdlib -ffreestanding \
  -T "$BT/link.ld" "$BT/crt0.S" "$BT/main.c" -o "$OUT/boot.elf"
echo "[run_smoke] boot.elf built: $OUT/boot.elf"

# 2. Build/update the Verilator sim through FuseSoC.  Do not guard this with
# an executable-exists check: that can silently run stale RTL after edits.
clean_args=()
if [[ "${PA_CLEAN:-0}" == "1" ]]; then
  clean_args+=(--clean)
fi
echo "[run_smoke] building Verilator sim via FuseSoC ..."
fusesoc --cores-root=sim/pa_smoke --cores-root=rtl/soc \
  --cores-root=rtl/ibex-orig \
  run --target=sim "${clean_args[@]}" --build pocketai:pa:pa_smoke

if [[ ! -x "$SIM" ]]; then
  echo "[run_smoke] FAIL: simulator was not produced: $SIM" >&2
  exit 1
fi

# 3. Run the sim, loading the ELF into RAM (registered as "ram" @0x0).
#    Run from the sim dir so the UART log (pa_smoke.log) lands there.
echo "[run_smoke] running simulation ..."
rm -f "$SIMDIR/pa_smoke.log"
(cd "$SIMDIR" && ./Vpa_smoke_top --meminit="ram,$ROOT/$OUT/boot.elf" >/dev/null 2>&1)

echo "=== UART capture (pa_smoke.log) ==="
cat "$SIMDIR/pa_smoke.log"
