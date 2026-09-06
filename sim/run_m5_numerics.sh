#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_NUM_BUILD=$(mktemp -d "$ROOT/build/m5_numerics.XXXXXX")
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
  -Iruntime/m5 runtime/m5/pa_m5_numerics.c runtime/m5/pa_m5_model.c \
  runtime/m5/pa_m5_ops.c runtime/m5/pa_m5_runtime.c tests/m5/model_ops_host.c \
  zynq/m4_cpu_sfpu.c -lm \
  -o "$M5_NUM_BUILD/libpa_m5_numerics.so" \
  >"$M5_NUM_BUILD/host_build.log" 2>&1
PYTHONPATH="$ROOT" build/m4_venv/bin/python tests/m5/test_numerics.py --library "$M5_NUM_BUILD/libpa_m5_numerics.so" \
  2>&1 | tee "$M5_NUM_BUILD/test.log"
riscv32-unknown-elf-gcc -std=c11 -Os -march=rv32imc_zicsr -mabi=ilp32 \
  -ffreestanding -fno-fast-math -Wall -Wextra -Werror -Iruntime/m5 \
  -c runtime/m5/pa_m5_numerics.c -o "$M5_NUM_BUILD/pa_m5_numerics.rv32.o" \
  >"$M5_NUM_BUILD/rv32_build.log" 2>&1
riscv32-unknown-elf-gcc -std=c11 -Os -march=rv32imc_zicsr -mabi=ilp32 \
  -ffreestanding -fno-fast-math -Wall -Wextra -Werror -Iruntime/m5 \
  -c runtime/m5/pa_m5_model.c -o "$M5_NUM_BUILD/pa_m5_model.rv32.o" \
  >>"$M5_NUM_BUILD/rv32_build.log" 2>&1
riscv32-unknown-elf-gcc -std=c11 -Os -march=rv32imc_zicsr -mabi=ilp32 \
  -ffreestanding -fno-fast-math -Wall -Wextra -Werror -Iruntime/m5 \
  -c runtime/m5/pa_m5_ops.c -o "$M5_NUM_BUILD/pa_m5_ops.rv32.o" \
  >>"$M5_NUM_BUILD/rv32_build.log" 2>&1
riscv32-unknown-elf-gcc -std=c11 -Os -march=rv32imc_zicsr -mabi=ilp32 \
  -ffreestanding -fno-fast-math -Wall -Wextra -Werror -Iruntime/m5 \
  -c runtime/m5/pa_m5_runtime.c -o "$M5_NUM_BUILD/pa_m5_runtime.rv32.o" \
  >>"$M5_NUM_BUILD/rv32_build.log" 2>&1
riscv32-unknown-elf-readelf -A "$M5_NUM_BUILD/pa_m5_numerics.rv32.o" >"$M5_NUM_BUILD/rv32_attributes.log"
grep -q 'rv32i2p1_m2p0_c2p0_zicsr2p0' "$M5_NUM_BUILD/rv32_attributes.log"
riscv32-unknown-elf-size "$M5_NUM_BUILD/pa_m5_numerics.rv32.o" "$M5_NUM_BUILD/pa_m5_model.rv32.o" \
  "$M5_NUM_BUILD/pa_m5_ops.rv32.o" \
  "$M5_NUM_BUILD/pa_m5_runtime.rv32.o" \
  | tee "$M5_NUM_BUILD/rv32_size.log"
echo "M5 NUMERICS EVIDENCE $M5_NUM_BUILD"
