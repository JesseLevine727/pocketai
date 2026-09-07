#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
CONTEXT_BUILD=$(realpath -m "${M5_CONTEXT_BUILD:?set a fresh M5_CONTEXT_BUILD}")
if [[ -e "$CONTEXT_BUILD" ]]; then echo 'use a fresh context build' >&2; exit 1; fi
mkdir -p "$CONTEXT_BUILD"
CONTEXT_VARIANT=${M5_CONTEXT_VARIANT:-diagnostic}
python3 -m scripts.m5_context_sources "$CONTEXT_BUILD/generated" --variant "$CONTEXT_VARIANT"
CONTEXT_DUAL=0
CONTEXT_POSITION=0
CONTEXT_COMBINED=0
CONTEXT_MASKED=0
if [[ "$CONTEXT_VARIANT" = masked ]]; then CONTEXT_MASKED=1; fi
if [[ "$CONTEXT_VARIANT" = combined || "$CONTEXT_VARIANT" = masked ]]; then CONTEXT_COMBINED=1; fi
if [[ "$CONTEXT_VARIANT" = position || "$CONTEXT_VARIANT" = combined || "$CONTEXT_VARIANT" = masked ]]; then CONTEXT_POSITION=1; fi
if [[ "$CONTEXT_VARIANT" = dual || "$CONTEXT_VARIANT" = direct || "$CONTEXT_VARIANT" = position || "$CONTEXT_VARIANT" = combined || "$CONTEXT_VARIANT" = masked ]]; then CONTEXT_DUAL=1; CONTEXT_VARIANT=parallel; fi
riscv64-unknown-elf-gcc --version | head -1 >"$CONTEXT_BUILD/toolchain.txt"
CONTEXT_INCLUDES=(-Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar -Iruntime/m5_search -Iruntime/m5_tenth -Iruntime/m5_context)
CONTEXT_KINDS=(profile)
CONTEXT_CACHE=runtime/m5_scalar/cache.c
CONTEXT_EXTRA=()
CONTEXT_HOST_EXTRA=()
CONTEXT_VARIANT_FLAGS=()
CONTEXT_LINKER=firmware/m5/memory_test.ld
if [[ "$CONTEXT_VARIANT" != diagnostic ]]; then
  CONTEXT_KINDS=(runtime profile detail)
  CONTEXT_CACHE="$CONTEXT_BUILD/generated/cache.c"
  CONTEXT_EXTRA=(runtime/m5_context/ready_cache.c)
  CONTEXT_HOST_EXTRA=(tests/m5_context/host.c)
  if [[ "$CONTEXT_VARIANT" != ready ]]; then CONTEXT_EXTRA+=(runtime/m5_context/score_metadata.c); fi
  if [[ "$CONTEXT_VARIANT" = smooth || "$CONTEXT_VARIANT" = product || "$CONTEXT_VARIANT" = local || "$CONTEXT_VARIANT" = parallel ]]; then
    CONTEXT_EXTRA+=(runtime/m5_context/smooth_cache.c)
    CONTEXT_VARIANT_FLAGS=(-DPA_CONTEXT_SMOOTH_CACHE)
  fi
  if [[ "$CONTEXT_VARIANT" = product || "$CONTEXT_VARIANT" = local || "$CONTEXT_VARIANT" = parallel ]]; then CONTEXT_VARIANT_FLAGS+=(-DPA_CONTEXT_SCORE_PRODUCT); fi
  if [[ "$CONTEXT_VARIANT" = local || "$CONTEXT_VARIANT" = parallel ]]; then
    CONTEXT_VARIANT_FLAGS+=(-DPA_CONTEXT_LOCAL_SCORES)
    CONTEXT_EXTRA+=(runtime/m5_context/local_scores.c)
    CONTEXT_LINKER=runtime/m5_context/memory.ld
  fi
  if [[ "$CONTEXT_VARIANT" = parallel ]]; then CONTEXT_EXTRA+=(runtime/m5_context/parallel.c); fi
  if [[ "$CONTEXT_DUAL" = 1 ]]; then
    CONTEXT_EXTRA=(runtime/m5_context/ready_cache.c runtime/m5_context/score_parallel.c runtime/m5_context/smooth_cache.c runtime/m5_context/local_scores.c runtime/m5_context/parallel.c)
    CONTEXT_VARIANT_FLAGS+=(-DPA_CONTEXT_PARALLEL_VALUES)
  fi
  if [[ "$CONTEXT_POSITION" = 1 ]]; then CONTEXT_VARIANT_FLAGS+=(-DPA_CONTEXT_POSITION_VALUES); fi
  if [[ "$CONTEXT_COMBINED" = 1 ]]; then CONTEXT_VARIANT_FLAGS+=(-DPA_CONTEXT_COMBINED_SCORES); fi
  if [[ "$CONTEXT_MASKED" = 1 ]]; then
    CONTEXT_VARIANT_FLAGS+=(-DPA_CONTEXT_MASKED_VALUES)
    CONTEXT_LINKER=runtime/m5_context/memory_packed.ld
  fi
fi
for kind in "${CONTEXT_KINDS[@]}"; do
  CONTEXT_ENTRY="$CONTEXT_BUILD/generated/attention_profile.c"
  CONTEXT_FLAGS=()
  CONTEXT_DETAIL=()
  if [[ "$CONTEXT_VARIANT" = diagnostic || "$kind" = detail ]]; then
    CONTEXT_FLAGS=(-DPA_CONTEXT_DIAGNOSTIC)
    CONTEXT_DETAIL=(runtime/m5_context/attention_detail.c)
  fi
  if [[ "$kind" = runtime ]]; then CONTEXT_ENTRY="$CONTEXT_BUILD/generated/runtime_entry.c"; fi
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math -fstack-usage \
  "${CONTEXT_FLAGS[@]}" "${CONTEXT_VARIANT_FLAGS[@]}" -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror \
  -ffreestanding -fno-builtin -nostdlib -Wl,--fatal-warnings -T "$CONTEXT_LINKER" \
  "${CONTEXT_INCLUDES[@]}" firmware/m5/memory_test_start.S \
  "$CONTEXT_ENTRY" "$CONTEXT_BUILD/generated/numerics.c" \
  "$CONTEXT_BUILD/generated/attention_ops.c" "$CONTEXT_BUILD/generated/requant.c" \
  runtime/m5/pa_m5_model.c "$CONTEXT_BUILD/generated/runtime.c" "$CONTEXT_BUILD/generated/hardware.c" \
  "$CONTEXT_CACHE" "${CONTEXT_EXTRA[@]}" "${CONTEXT_DETAIL[@]}" -lgcc \
  -o "$CONTEXT_BUILD/m5_$kind.elf" >"$CONTEXT_BUILD/$kind.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$CONTEXT_BUILD/m5_$kind.elf" "$CONTEXT_BUILD/m5_$kind.bin"
  test "$(stat -c %s "$CONTEXT_BUILD/m5_$kind.bin")" = 65536
  test -z "$(riscv64-unknown-elf-nm -u "$CONTEXT_BUILD/m5_$kind.elf")"
  riscv64-unknown-elf-size "$CONTEXT_BUILD/m5_$kind.elf" | tee "$CONTEXT_BUILD/$kind.size.txt"
  riscv64-unknown-elf-readelf -A "$CONTEXT_BUILD/m5_$kind.elf" >"$CONTEXT_BUILD/$kind.attributes.txt"
done
CONTEXT_HOST_FLAGS=()
if [[ "$CONTEXT_VARIANT" = parallel ]]; then CONTEXT_HOST_FLAGS=(-DPA_CONTEXT_TEST_THREADS -pthread); fi
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math "${CONTEXT_HOST_FLAGS[@]}" \
  "${CONTEXT_VARIANT_FLAGS[@]}" \
  "${CONTEXT_INCLUDES[@]}" "$CONTEXT_BUILD/generated/numerics.c" \
  "$CONTEXT_BUILD/generated/attention_ops.c" "$CONTEXT_BUILD/generated/requant.c" \
  runtime/m5/pa_m5_model.c "$CONTEXT_BUILD/generated/runtime.c" tests/m5/model_ops_host.c \
  tests/m5_scalar/quantize_host.c zynq/m4_cpu_sfpu.c "$CONTEXT_CACHE" \
  "${CONTEXT_EXTRA[@]}" "${CONTEXT_HOST_EXTRA[@]}" -lm -o "$CONTEXT_BUILD/native.so"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_scalar.test_attention \
  --candidate "$CONTEXT_BUILD/native.so" | tee "$CONTEXT_BUILD/attention_test.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 \
  build/m4_venv/bin/python tests/m5/test_numerics.py --library "$CONTEXT_BUILD/native.so" | tee "$CONTEXT_BUILD/native_test.log"
if [[ "$CONTEXT_VARIANT" != diagnostic ]]; then
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 build/m4_venv/bin/python \
    -m tests.m5_context.test_ready --candidate "$CONTEXT_BUILD/native.so" | tee "$CONTEXT_BUILD/ready_test.log"
fi
if [[ "$CONTEXT_VARIANT" != diagnostic && "$CONTEXT_VARIANT" != ready ]]; then
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_context.test_score_metadata \
    --candidate "$CONTEXT_BUILD/native.so" | tee "$CONTEXT_BUILD/score_test.log"
fi
if [[ "$CONTEXT_VARIANT" = product || "$CONTEXT_VARIANT" = local || "$CONTEXT_VARIANT" = parallel ]]; then
  gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -Iruntime/m5_context -Iruntime/m5_tenth \
    tests/m5_context/product_host.c -o "$CONTEXT_BUILD/product_host.so"
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_context.test_product \
    --library "$CONTEXT_BUILD/product_host.so" | tee "$CONTEXT_BUILD/product_test.log"
fi
if [[ "$CONTEXT_VARIANT" = local || "$CONTEXT_VARIANT" = parallel ]]; then
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_context.test_local_scores \
    --candidate "$CONTEXT_BUILD/native.so" | tee "$CONTEXT_BUILD/local_score_test.log"
fi
if [[ "$CONTEXT_COMBINED" = 1 ]]; then
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_context.test_combined \
    --candidate "$CONTEXT_BUILD/native.so" | tee "$CONTEXT_BUILD/combined_test.log"
fi
echo 'M5 CONTEXT BUILD PASS'
