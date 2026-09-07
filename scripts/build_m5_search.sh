#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
SEARCH_BUILD=$(realpath -m "${M5_SEARCH_BUILD:?set a fresh M5_SEARCH_BUILD}")
SEARCH_VARIANT=${M5_SEARCH_VARIANT:?set M5_SEARCH_VARIANT}
if [[ -e "$SEARCH_BUILD" ]]; then echo 'use a fresh search build' >&2; exit 1; fi
mkdir -p "$SEARCH_BUILD"
python3 -m scripts.m5_search_sources "$SEARCH_BUILD/generated" --variant "$SEARCH_VARIANT"
riscv64-unknown-elf-gcc --version | head -1 >"$SEARCH_BUILD/toolchain.txt"
SEARCH_OPT=()
if [[ "$SEARCH_VARIANT" = lto ]]; then SEARCH_OPT=(-flto); fi
for kind in runtime profile fine; do
  SEARCH_ENTRY=firmware/m5/runtime_firmware.c
  SEARCH_OPS="$SEARCH_BUILD/generated/ops.c"
  SEARCH_NUMERIC="$SEARCH_BUILD/generated/numerics.c"
  SEARCH_PROFILE_EXTRA=()
  if [[ "$kind" = profile ]]; then SEARCH_ENTRY="$SEARCH_BUILD/generated/profile.c"; fi
  if [[ "$kind" = fine ]]; then
    SEARCH_ENTRY="$SEARCH_BUILD/generated/fine_profile.c"
    SEARCH_OPS="$SEARCH_BUILD/generated/fine_ops.c"
    SEARCH_NUMERIC="$SEARCH_BUILD/generated/fine_numerics.c"
    SEARCH_PROFILE_EXTRA=(runtime/m5_fast/pa_m5_fine_profile.c)
  fi
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math "${SEARCH_OPT[@]}" \
    -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin \
    -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
    -Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar -Iruntime/m5_search \
    firmware/m5/memory_test_start.S "$SEARCH_ENTRY" "$SEARCH_NUMERIC" \
    "$SEARCH_OPS" "$SEARCH_BUILD/generated/requant.c" \
    runtime/m5/pa_m5_model.c "$SEARCH_BUILD/generated/runtime.c" "$SEARCH_BUILD/generated/hardware.c" \
    runtime/m5_scalar/cache.c "${SEARCH_PROFILE_EXTRA[@]}" -lgcc \
    -o "$SEARCH_BUILD/m5_$kind.elf" >"$SEARCH_BUILD/$kind.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$SEARCH_BUILD/m5_$kind.elf" "$SEARCH_BUILD/m5_$kind.bin"
  test "$(stat -c %s "$SEARCH_BUILD/m5_$kind.bin")" = 65536
  test -z "$(riscv64-unknown-elf-nm -u "$SEARCH_BUILD/m5_$kind.elf")"
  riscv64-unknown-elf-size "$SEARCH_BUILD/m5_$kind.elf" | tee "$SEARCH_BUILD/$kind.size.txt"
  riscv64-unknown-elf-readelf -A "$SEARCH_BUILD/m5_$kind.elf" >"$SEARCH_BUILD/$kind.attributes.txt"
done
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math "${SEARCH_OPT[@]}" \
  -Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar -Iruntime/m5_search "$SEARCH_BUILD/generated/numerics.c" \
  "$SEARCH_BUILD/generated/ops.c" "$SEARCH_BUILD/generated/requant.c" \
  runtime/m5/pa_m5_model.c "$SEARCH_BUILD/generated/runtime.c" tests/m5/model_ops_host.c \
  tests/m5_scalar/quantize_host.c zynq/m4_cpu_sfpu.c runtime/m5_scalar/cache.c -lm -o "$SEARCH_BUILD/native.so"
python3 -m tests.m5_scalar.test_quantize --candidate "$SEARCH_BUILD/native.so" | tee "$SEARCH_BUILD/quantize_test.log"
python3 -m tests.m5_scalar.test_cache --candidate "$SEARCH_BUILD/native.so" | tee "$SEARCH_BUILD/cache_test.log"
python3 -m tests.m5_iterate.test_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$SEARCH_BUILD/native.so" | tee "$SEARCH_BUILD/norm_factor.log"
python3 -m tests.m5_opt.test_exact_numerics --baseline build/m5_fast_runtime_requant_v1/native.so \
  --candidate "$SEARCH_BUILD/native.so" | tee "$SEARCH_BUILD/exact_numerics.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 \
  build/m4_venv/bin/python tests/m5/test_numerics.py --library "$SEARCH_BUILD/native.so" | tee "$SEARCH_BUILD/native_test.log"
sha256sum "$SEARCH_BUILD/generated/"* "$SEARCH_BUILD/"*.bin scripts/m5_search_sources.py scripts/build_m5_search.sh \
  >"$SEARCH_BUILD/artifacts.sha256"
echo "M5 SEARCH BUILD AND EXACT REGRESSION PASS $SEARCH_VARIANT $SEARCH_BUILD"
