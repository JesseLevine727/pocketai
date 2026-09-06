#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
M5_OPT_BUILD=$(realpath -m "${M5_OPT_RUNTIME_BUILD:-$ROOT/build/m5_opt_runtime}")
if [[ -e "$M5_OPT_BUILD" ]]; then echo 'use a fresh optimized runtime build' >&2; exit 1; fi
mkdir -p "$M5_OPT_BUILD"
riscv64-unknown-elf-gcc --version | head -1 >"$M5_OPT_BUILD/toolchain.txt"
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding \
  -fno-builtin -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
  -Iruntime/m5 firmware/m5/memory_test_start.S firmware/m5/runtime_firmware.c \
  runtime/m5_opt/pa_m5_metadata_opt.c runtime/m5/pa_m5_model.c \
  runtime/m5_opt/pa_m5_ops_opt.c runtime/m5/pa_m5_runtime.c runtime/m5/pa_m5_hw.c \
  -lgcc -o "$M5_OPT_BUILD/m5_runtime.elf" >"$M5_OPT_BUILD/build.log" 2>&1
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_OPT_BUILD/m5_runtime.elf" "$M5_OPT_BUILD/m5_runtime.bin"
test "$(stat -c %s "$M5_OPT_BUILD/m5_runtime.bin")" = 65536
test -z "$(riscv64-unknown-elf-nm -u "$M5_OPT_BUILD/m5_runtime.elf")"
riscv64-unknown-elf-readelf -A "$M5_OPT_BUILD/m5_runtime.elf" >"$M5_OPT_BUILD/attributes.txt"
riscv64-unknown-elf-size "$M5_OPT_BUILD/m5_runtime.elf" | tee "$M5_OPT_BUILD/size.txt"
sha256sum firmware/m5/runtime_firmware.c firmware/m5/memory_test_start.S \
  firmware/m5/memory_test.ld runtime/m5_opt/*.c runtime/m5/*.c runtime/m5/*.h \
  scripts/build_m5_opt_runtime.sh "$M5_OPT_BUILD/m5_runtime.bin" \
  >"$M5_OPT_BUILD/sha256.txt"
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
  -Iruntime/m5 runtime/m5_opt/pa_m5_metadata_opt.c runtime/m5/pa_m5_model.c \
  runtime/m5_opt/pa_m5_ops_opt.c runtime/m5/pa_m5_runtime.c tests/m5/model_ops_host.c \
  zynq/m4_cpu_sfpu.c -lm -o "$M5_OPT_BUILD/native.so"
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
  -Iruntime/m5 runtime/m5/pa_m5_numerics.c -o "$M5_OPT_BUILD/baseline_numerics.so"
python3 -m tests.m5_opt.test_exact_numerics --baseline "$M5_OPT_BUILD/baseline_numerics.so" \
  --candidate "$M5_OPT_BUILD/native.so" | tee "$M5_OPT_BUILD/exact_test.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 \
  build/m4_venv/bin/python tests/m5/test_numerics.py --library "$M5_OPT_BUILD/native.so" \
  | tee "$M5_OPT_BUILD/native_test.log"
echo "M5 OPT RUNTIME BUILD AND NATIVE REGRESSION PASS $M5_OPT_BUILD"
