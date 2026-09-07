#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
M5_FAST_RUNTIME_BUILD=$(realpath -m "${M5_FAST_RUNTIME_BUILD:-$ROOT/build/m5_fast_runtime_v1}")
if [[ -e "$M5_FAST_RUNTIME_BUILD" ]]; then echo 'use a fresh runtime build' >&2; exit 1; fi
mkdir -p "$M5_FAST_RUNTIME_BUILD"
M5_FAST_SOURCE_FLAGS=(--prepare)
M5_FAST_EXTRA_SOURCES=()
if [[ "${M5_FAST_REQUANT:-0}" = 1 ]]; then
  M5_FAST_SOURCE_FLAGS+=(--requant)
  M5_FAST_EXTRA_SOURCES+=(runtime/m5_fast/pa_m5_requant.c)
fi
python3 -m scripts.m5_fast_firmware_sources "$M5_FAST_RUNTIME_BUILD/generated" "${M5_FAST_SOURCE_FLAGS[@]}"
riscv64-unknown-elf-gcc --version | head -1 >"$M5_FAST_RUNTIME_BUILD/toolchain.txt"
for kind in runtime profile; do
  M5_FAST_ENTRY=firmware/m5/runtime_firmware.c
  if [[ "$kind" = profile ]]; then M5_FAST_ENTRY="$M5_FAST_RUNTIME_BUILD/generated/profile.c"; fi
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
    -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin \
    -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld -Iruntime/m5 -Iruntime/m5_fast \
    firmware/m5/memory_test_start.S "$M5_FAST_ENTRY" "$M5_FAST_RUNTIME_BUILD/generated/numerics.c" \
    "$M5_FAST_RUNTIME_BUILD/generated/ops.c" "${M5_FAST_EXTRA_SOURCES[@]}" \
    runtime/m5/pa_m5_model.c runtime/m5/pa_m5_runtime.c runtime/m5/pa_m5_hw.c -lgcc \
    -o "$M5_FAST_RUNTIME_BUILD/m5_$kind.elf" >"$M5_FAST_RUNTIME_BUILD/$kind.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$M5_FAST_RUNTIME_BUILD/m5_$kind.elf" "$M5_FAST_RUNTIME_BUILD/m5_$kind.bin"
  test "$(stat -c %s "$M5_FAST_RUNTIME_BUILD/m5_$kind.bin")" = 65536
  test -z "$(riscv64-unknown-elf-nm -u "$M5_FAST_RUNTIME_BUILD/m5_$kind.elf")"
  riscv64-unknown-elf-readelf -A "$M5_FAST_RUNTIME_BUILD/m5_$kind.elf" >"$M5_FAST_RUNTIME_BUILD/$kind.attributes.txt"
  riscv64-unknown-elf-size "$M5_FAST_RUNTIME_BUILD/m5_$kind.elf" | tee "$M5_FAST_RUNTIME_BUILD/$kind.size.txt"
done
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
  -Iruntime/m5 -Iruntime/m5_fast "$M5_FAST_RUNTIME_BUILD/generated/numerics.c" \
  "$M5_FAST_RUNTIME_BUILD/generated/ops.c" "${M5_FAST_EXTRA_SOURCES[@]}" \
  runtime/m5/pa_m5_model.c runtime/m5/pa_m5_runtime.c tests/m5/model_ops_host.c \
  zynq/m4_cpu_sfpu.c -lm -o "$M5_FAST_RUNTIME_BUILD/native.so"
sha256sum "$M5_FAST_RUNTIME_BUILD/generated/"* "$M5_FAST_RUNTIME_BUILD/"*.bin \
  firmware/m5/runtime_firmware.c runtime/m5_fast/* runtime/m5/*.c runtime/m5/*.h \
  scripts/m5_fast_firmware_sources.py scripts/build_m5_fast_runtime.sh \
  >"$M5_FAST_RUNTIME_BUILD/artifacts.sha256"
python3 -m tests.m5_opt.test_exact_numerics --baseline build/m5_opt_runtime/baseline_numerics.so \
  --candidate "$M5_FAST_RUNTIME_BUILD/native.so" | tee "$M5_FAST_RUNTIME_BUILD/exact_numerics.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 \
  build/m4_venv/bin/python tests/m5/test_numerics.py --library "$M5_FAST_RUNTIME_BUILD/native.so" \
  | tee "$M5_FAST_RUNTIME_BUILD/native_test.log"
echo "M5 FAST RUNTIME BUILD AND NATIVE REGRESSION PASS $M5_FAST_RUNTIME_BUILD"
