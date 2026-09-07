#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
TENTH_BUILD=$(realpath -m "${M5_TENTH_BUILD:?set a fresh M5_TENTH_BUILD}")
TENTH_VARIANT=${M5_TENTH_VARIANT:?set M5_TENTH_VARIANT}
if [[ -e "$TENTH_BUILD" ]]; then echo 'use a fresh search build' >&2; exit 1; fi
mkdir -p "$TENTH_BUILD"
python3 -m scripts.m5_tenth_sources "$TENTH_BUILD/generated" --variant "$TENTH_VARIANT"
riscv64-unknown-elf-gcc --version | head -1 >"$TENTH_BUILD/toolchain.txt"
TENTH_OPT=()
for kind in runtime profile fine; do
  TENTH_ENTRY=firmware/m5/runtime_firmware.c
  TENTH_OPS="$TENTH_BUILD/generated/ops.c"
  TENTH_NUMERIC="$TENTH_BUILD/generated/numerics.c"
  TENTH_PROFILE_EXTRA=()
  if [[ "$kind" = profile ]]; then TENTH_ENTRY="$TENTH_BUILD/generated/profile.c"; fi
  if [[ "$kind" = fine ]]; then
    TENTH_ENTRY="$TENTH_BUILD/generated/fine_profile.c"
    TENTH_OPS="$TENTH_BUILD/generated/fine_ops.c"
    TENTH_NUMERIC="$TENTH_BUILD/generated/fine_numerics.c"
    TENTH_PROFILE_EXTRA=(runtime/m5_fast/pa_m5_fine_profile.c)
  fi
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math "${TENTH_OPT[@]}" \
    -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin \
    -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
    -Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar -Iruntime/m5_search -Iruntime/m5_tenth \
    firmware/m5/memory_test_start.S "$TENTH_ENTRY" "$TENTH_NUMERIC" \
    "$TENTH_OPS" "$TENTH_BUILD/generated/requant.c" \
    runtime/m5/pa_m5_model.c "$TENTH_BUILD/generated/runtime.c" "$TENTH_BUILD/generated/hardware.c" \
    runtime/m5_scalar/cache.c "${TENTH_PROFILE_EXTRA[@]}" -lgcc \
    -o "$TENTH_BUILD/m5_$kind.elf" >"$TENTH_BUILD/$kind.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$TENTH_BUILD/m5_$kind.elf" "$TENTH_BUILD/m5_$kind.bin"
  test "$(stat -c %s "$TENTH_BUILD/m5_$kind.bin")" = 65536
  test -z "$(riscv64-unknown-elf-nm -u "$TENTH_BUILD/m5_$kind.elf")"
  riscv64-unknown-elf-size "$TENTH_BUILD/m5_$kind.elf" | tee "$TENTH_BUILD/$kind.size.txt"
  riscv64-unknown-elf-readelf -A "$TENTH_BUILD/m5_$kind.elf" >"$TENTH_BUILD/$kind.attributes.txt"
done
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math "${TENTH_OPT[@]}" \
  -Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar -Iruntime/m5_search -Iruntime/m5_tenth "$TENTH_BUILD/generated/numerics.c" \
  "$TENTH_BUILD/generated/ops.c" "$TENTH_BUILD/generated/requant.c" \
  runtime/m5/pa_m5_model.c "$TENTH_BUILD/generated/runtime.c" tests/m5/model_ops_host.c \
  tests/m5_scalar/quantize_host.c zynq/m4_cpu_sfpu.c runtime/m5_scalar/cache.c -lm -o "$TENTH_BUILD/native.so"
python3 -m tests.m5_scalar.test_quantize --candidate "$TENTH_BUILD/native.so" | tee "$TENTH_BUILD/quantize_test.log"
python3 -m tests.m5_scalar.test_cache --candidate "$TENTH_BUILD/native.so" | tee "$TENTH_BUILD/cache_test.log"
python3 -m tests.m5_tenth.test_round --candidate "$TENTH_BUILD/native.so" | tee "$TENTH_BUILD/round_test.log"
python3 -m tests.m5_iterate.test_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$TENTH_BUILD/native.so" | tee "$TENTH_BUILD/norm_factor.log"
python3 -m tests.m5_opt.test_exact_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$TENTH_BUILD/native.so" | tee "$TENTH_BUILD/exact_numerics.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 \
  build/m4_venv/bin/python tests/m5/test_numerics.py --library "$TENTH_BUILD/native.so" | tee "$TENTH_BUILD/native_test.log"
sha256sum "$TENTH_BUILD/generated/"* "$TENTH_BUILD/"*.bin scripts/m5_tenth_sources.py scripts/build_m5_tenth.sh \
  >"$TENTH_BUILD/artifacts.sha256"
echo "M5 TENTH BUILD AND EXACT REGRESSION PASS $TENTH_VARIANT $TENTH_BUILD"
