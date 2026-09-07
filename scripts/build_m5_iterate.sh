#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
ITER_BUILD=$(realpath -m "${M5_ITER_BUILD:?set a fresh M5_ITER_BUILD}")
ITER_VARIANT=${M5_ITER_VARIANT:?set M5_ITER_VARIANT}
if [[ -e "$ITER_BUILD" ]]; then echo 'use a fresh iteration build' >&2; exit 1; fi
mkdir -p "$ITER_BUILD"
python3 -m scripts.m5_iterate_sources "$ITER_BUILD/generated" --variant "$ITER_VARIANT"
riscv64-unknown-elf-gcc --version | head -1 >"$ITER_BUILD/toolchain.txt"
for kind in runtime profile; do
  ITER_ENTRY=firmware/m5/runtime_firmware.c
  if [[ "$kind" = profile ]]; then ITER_ENTRY="$ITER_BUILD/generated/profile.c"; fi
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
    -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin \
    -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld -Iruntime/m5 -Iruntime/m5_fast \
    firmware/m5/memory_test_start.S "$ITER_ENTRY" "$ITER_BUILD/generated/numerics.c" \
    "$ITER_BUILD/generated/ops.c" runtime/m5_fast/pa_m5_requant.c \
    runtime/m5/pa_m5_model.c runtime/m5/pa_m5_runtime.c "$ITER_BUILD/generated/hardware.c" -lgcc \
    -o "$ITER_BUILD/m5_$kind.elf" >"$ITER_BUILD/$kind.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$ITER_BUILD/m5_$kind.elf" "$ITER_BUILD/m5_$kind.bin"
  test "$(stat -c %s "$ITER_BUILD/m5_$kind.bin")" = 65536
  test -z "$(riscv64-unknown-elf-nm -u "$ITER_BUILD/m5_$kind.elf")"
  riscv64-unknown-elf-readelf -A "$ITER_BUILD/m5_$kind.elf" >"$ITER_BUILD/$kind.attributes.txt"
  riscv64-unknown-elf-size "$ITER_BUILD/m5_$kind.elf" | tee "$ITER_BUILD/$kind.size.txt"
done
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
  -Iruntime/m5 -Iruntime/m5_fast "$ITER_BUILD/generated/numerics.c" \
  "$ITER_BUILD/generated/ops.c" runtime/m5_fast/pa_m5_requant.c \
  runtime/m5/pa_m5_model.c runtime/m5/pa_m5_runtime.c tests/m5/model_ops_host.c \
  zynq/m4_cpu_sfpu.c -lm -o "$ITER_BUILD/native.so"
sha256sum "$ITER_BUILD/generated/"* "$ITER_BUILD/"*.bin \
  runtime/m5_iterate/* scripts/m5_iterate_sources.py scripts/build_m5_iterate.sh \
  >"$ITER_BUILD/artifacts.sha256"
python3 -m tests.m5_opt.test_exact_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$ITER_BUILD/native.so" | tee "$ITER_BUILD/exact_numerics.log"
python3 -m tests.m5_iterate.test_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$ITER_BUILD/native.so" | tee "$ITER_BUILD/norm_factor.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 \
  build/m4_venv/bin/python tests/m5/test_numerics.py --library "$ITER_BUILD/native.so" \
  | tee "$ITER_BUILD/native_test.log"
echo "M5 ITERATE BUILD AND EXACT REGRESSION PASS $ITER_VARIANT $ITER_BUILD"
