#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_ACCEL_BUILD=$(mktemp -d "$ROOT/build/m5_cluster_accelerators.XXXXXX")
riscv32-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -nostdlib -ffreestanding \
  -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
  firmware/m5/memory_test_start.S firmware/m5/accelerator_test.c -o "$M5_ACCEL_BUILD/accelerators.elf" \
  >"$M5_ACCEL_BUILD/firmware.log" 2>&1
riscv32-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_ACCEL_BUILD/accelerators.elf" "$M5_ACCEL_BUILD/accelerators.bin"
fusesoc --cores-root=sim/pa_m5_cluster --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim --work-root="$M5_ACCEL_BUILD/sim" --build pocketai:pa:pa_m5_accelerators \
  >"$M5_ACCEL_BUILD/build.log" 2>&1 || { tail -n 80 "$M5_ACCEL_BUILD/build.log"; exit 1; }
(cd "$M5_ACCEL_BUILD/sim" && ./Vpa_m5_cluster_top "$M5_ACCEL_BUILD/accelerators.bin") \
  2>&1 | tee "$M5_ACCEL_BUILD/test.log"
echo "M5 ACTUAL IBEX ACCELERATOR EVIDENCE $M5_ACCEL_BUILD"
