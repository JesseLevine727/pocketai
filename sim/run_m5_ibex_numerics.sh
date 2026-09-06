#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_IBEX_NUM=$(mktemp -d "$ROOT/build/m5_ibex_numerics.XXXXXX")
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -Os -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin \
  -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld -Iruntime/m5 \
  firmware/m5/memory_test_start.S firmware/m5/numerics_test.c runtime/m5/pa_m5_numerics.c \
  -lgcc -o "$M5_IBEX_NUM/numerics.elf" >"$M5_IBEX_NUM/firmware.log" 2>&1
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_IBEX_NUM/numerics.elf" "$M5_IBEX_NUM/numerics.bin"
test "$(stat -c %s "$M5_IBEX_NUM/numerics.bin")" = 65536
fusesoc --cores-root=sim/pa_m5_cluster --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim --work-root="$M5_IBEX_NUM/sim" --build pocketai:pa:pa_m5_numerics \
  >"$M5_IBEX_NUM/build.log" 2>&1 || { tail -n 80 "$M5_IBEX_NUM/build.log"; exit 1; }
(cd "$M5_IBEX_NUM/sim" && ./Vpa_m5_cluster_top "$M5_IBEX_NUM/numerics.bin") \
  2>&1 | tee "$M5_IBEX_NUM/test.log"
riscv64-unknown-elf-size "$M5_IBEX_NUM/numerics.elf" | tee "$M5_IBEX_NUM/size.log"
echo "M5 ACTUAL IBEX NUMERICS EVIDENCE $M5_IBEX_NUM"
