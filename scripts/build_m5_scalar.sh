#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
SCALAR_BUILD=$(realpath -m "${M5_SCALAR_BUILD:?set a fresh M5_SCALAR_BUILD}")
SCALAR_VARIANT=${M5_SCALAR_VARIANT:?set M5_SCALAR_VARIANT}
if [[ -e "$SCALAR_BUILD" ]]; then echo 'use a fresh scalar build' >&2; exit 1; fi
mkdir -p "$SCALAR_BUILD"
python3 -m scripts.m5_scalar_sources "$SCALAR_BUILD/generated" --variant "$SCALAR_VARIANT"
riscv64-unknown-elf-gcc --version | head -1 >"$SCALAR_BUILD/toolchain.txt"
SCALAR_EXTRA=()
if [[ "$SCALAR_VARIANT" = lookup || "$SCALAR_VARIANT" = metadata || "$SCALAR_VARIANT" = affine ]]; then SCALAR_EXTRA=(runtime/m5_scalar/cache.c); fi
for kind in runtime profile fine; do
  SCALAR_ENTRY=firmware/m5/runtime_firmware.c
  SCALAR_OPS="$SCALAR_BUILD/generated/ops.c"
  SCALAR_NUMERIC="$SCALAR_BUILD/generated/numerics.c"
  SCALAR_PROFILE_EXTRA=()
  if [[ "$kind" = profile ]]; then SCALAR_ENTRY="$SCALAR_BUILD/generated/profile.c"; fi
  if [[ "$kind" = fine ]]; then
    SCALAR_ENTRY="$SCALAR_BUILD/generated/fine_profile.c"
    SCALAR_OPS="$SCALAR_BUILD/generated/fine_ops.c"
    SCALAR_NUMERIC="$SCALAR_BUILD/generated/fine_numerics.c"
    SCALAR_PROFILE_EXTRA=(runtime/m5_fast/pa_m5_fine_profile.c)
  fi
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
    -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin \
    -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
    -Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar \
    firmware/m5/memory_test_start.S "$SCALAR_ENTRY" "$SCALAR_NUMERIC" \
    "$SCALAR_OPS" "$SCALAR_BUILD/generated/requant.c" \
    runtime/m5/pa_m5_model.c "$SCALAR_BUILD/generated/runtime.c" "$SCALAR_BUILD/generated/hardware.c" \
    "${SCALAR_EXTRA[@]}" "${SCALAR_PROFILE_EXTRA[@]}" -lgcc \
    -o "$SCALAR_BUILD/m5_$kind.elf" >"$SCALAR_BUILD/$kind.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$SCALAR_BUILD/m5_$kind.elf" "$SCALAR_BUILD/m5_$kind.bin"
  test "$(stat -c %s "$SCALAR_BUILD/m5_$kind.bin")" = 65536
  test -z "$(riscv64-unknown-elf-nm -u "$SCALAR_BUILD/m5_$kind.elf")"
  riscv64-unknown-elf-size "$SCALAR_BUILD/m5_$kind.elf" | tee "$SCALAR_BUILD/$kind.size.txt"
  riscv64-unknown-elf-readelf -A "$SCALAR_BUILD/m5_$kind.elf" >"$SCALAR_BUILD/$kind.attributes.txt"
done
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
  -Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar "$SCALAR_BUILD/generated/numerics.c" \
  "$SCALAR_BUILD/generated/ops.c" "$SCALAR_BUILD/generated/requant.c" \
  runtime/m5/pa_m5_model.c "$SCALAR_BUILD/generated/runtime.c" tests/m5/model_ops_host.c \
  tests/m5_scalar/quantize_host.c zynq/m4_cpu_sfpu.c "${SCALAR_EXTRA[@]}" -lm -o "$SCALAR_BUILD/native.so"
python3 -m tests.m5_scalar.test_quantize --candidate "$SCALAR_BUILD/native.so" \
  | tee "$SCALAR_BUILD/quantize_test.log"
if [[ ${#SCALAR_EXTRA[@]} -gt 0 ]]; then
  python3 -m tests.m5_scalar.test_cache --candidate "$SCALAR_BUILD/native.so" \
    | tee "$SCALAR_BUILD/cache_test.log"
fi
python3 -m tests.m5_iterate.test_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$SCALAR_BUILD/native.so" | tee "$SCALAR_BUILD/norm_factor.log"
python3 -m tests.m5_opt.test_exact_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$SCALAR_BUILD/native.so" | tee "$SCALAR_BUILD/exact_numerics.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 \
  build/m4_venv/bin/python tests/m5/test_numerics.py --library "$SCALAR_BUILD/native.so" \
  | tee "$SCALAR_BUILD/native_test.log"
sha256sum "$SCALAR_BUILD/generated/"* "$SCALAR_BUILD/"*.bin \
  runtime/m5_scalar/* scripts/m5_scalar_sources.py scripts/build_m5_scalar.sh \
  >"$SCALAR_BUILD/artifacts.sha256"
echo "M5 SCALAR BUILD AND EXACT REGRESSION PASS $SCALAR_VARIANT $SCALAR_BUILD"
