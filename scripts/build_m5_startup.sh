#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
STARTUP_BUILD=$(realpath -m "${M5_STARTUP_BUILD:?set a fresh M5_STARTUP_BUILD}")
if [[ -e "$STARTUP_BUILD" ]]; then echo 'use a fresh startup build' >&2; exit 1; fi
mkdir -p "$STARTUP_BUILD"
STARTUP_VARIANT=${M5_STARTUP_VARIANT:-baseline}
STARTUP_REQUESTED_VARIANT=$STARTUP_VARIANT
if [[ "$STARTUP_VARIANT" = inline_fixed || "$STARTUP_VARIANT" = inline_product || "$STARTUP_VARIANT" = bias_reuse || "$STARTUP_VARIANT" = residual_fixed || "$STARTUP_VARIANT" = rolling_fixed || "$STARTUP_VARIANT" = local_rows || "$STARTUP_VARIANT" = local_bias ]]; then STARTUP_VARIANT=split_fixed; fi
STARTUP_KINDS=(runtime profile detail)
STARTUP_SPLIT=0
if [[ "$STARTUP_VARIANT" = split_fixed ]]; then STARTUP_SPLIT=1; STARTUP_KINDS+=(trace); fi
STARTUP_TEST_BRANCH=0
STARTUP_TEST_BATCH=0
STARTUP_TEST_FIXED=0
if [[ "$STARTUP_VARIANT" = fixed_branch || "$STARTUP_VARIANT" = split_fixed ]]; then STARTUP_TEST_FIXED=1; fi
case "$STARTUP_VARIANT" in
  batch_project|implicit_product|lazy_values|scalar_batch|certified_branch|packed_attention|fixed_branch|split_fixed) STARTUP_TEST_BATCH=1 ;;
esac
if [[ "$STARTUP_VARIANT" = certified_branch ]]; then STARTUP_TEST_BRANCH=1; fi
STARTUP_READY_TEST=tests.m5_context.test_ready
if [[ "$STARTUP_VARIANT" = lazy_values || "$STARTUP_VARIANT" = scalar_batch || "$STARTUP_VARIANT" = certified_branch || "$STARTUP_VARIANT" = packed_attention || "$STARTUP_VARIANT" = fixed_branch || "$STARTUP_VARIANT" = split_fixed ]]; then STARTUP_READY_TEST=tests.m5_startup.test_lazy; fi
STARTUP_TEST_IMPLICIT=0
if [[ "$STARTUP_VARIANT" = implicit_product || "$STARTUP_VARIANT" = scalar_batch || "$STARTUP_VARIANT" = certified_branch || "$STARTUP_VARIANT" = packed_attention || "$STARTUP_VARIANT" = fixed_branch || "$STARTUP_VARIANT" = split_fixed ]]; then STARTUP_TEST_IMPLICIT=1; fi
python3 -m scripts.m5_startup_sources "$STARTUP_BUILD/generated" --variant "$STARTUP_REQUESTED_VARIANT"
STARTUP_BOOT=firmware/m5/memory_test_start.S
if [[ "${M5_STARTUP_ICACHE:-0}" = 1 ]]; then
  STARTUP_BOOT="$STARTUP_BUILD/generated/icache_start.S"
  python3 -m scripts.m5_startup_icache "$STARTUP_BOOT" --emit-start
fi
STARTUP_LINKER=runtime/m5_context/memory_packed.ld
if [[ "$STARTUP_SPLIT" = 1 ]]; then STARTUP_LINKER="$STARTUP_BUILD/generated/memory.ld"; fi
if [[ "$STARTUP_VARIANT" = scalar_batch || "$STARTUP_VARIANT" = certified_branch || "$STARTUP_VARIANT" = packed_attention || "$STARTUP_VARIANT" = fixed_branch || "$STARTUP_VARIANT" = split_fixed ]]; then STARTUP_VARIANT=extrema_scan; fi
# Test feature inheritance; source derivation records the requested variant.
if [[ "$STARTUP_VARIANT" = smooth_once || "$STARTUP_VARIANT" = quant_parallel || "$STARTUP_VARIANT" = word_affine || "$STARTUP_VARIANT" = cold_features || "$STARTUP_VARIANT" = leaf_profile || "$STARTUP_VARIANT" = range_hint || "$STARTUP_VARIANT" = batch_project || "$STARTUP_VARIANT" = implicit_product || "$STARTUP_VARIANT" = lazy_values ]]; then STARTUP_VARIANT=extrema_scan; fi
STARTUP_GC=()
if [[ "$STARTUP_VARIANT" != baseline && "$STARTUP_VARIANT" != cold_parallel ]]; then STARTUP_GC=(-ffunction-sections -fdata-sections -Wl,--gc-sections); fi
STARTUP_INCLUDES=(-Iruntime/m5_startup -Iruntime/m5 -Iruntime/m5_fast -Iruntime/m5_scalar -Iruntime/m5_search -Iruntime/m5_tenth -Iruntime/m5_context)
STARTUP_FLAGS=(-DPA_CONTEXT_SMOOTH_CACHE -DPA_CONTEXT_SCORE_PRODUCT -DPA_CONTEXT_LOCAL_SCORES -DPA_CONTEXT_PARALLEL_VALUES -DPA_CONTEXT_POSITION_VALUES -DPA_CONTEXT_COMBINED_SCORES -DPA_CONTEXT_MASKED_VALUES)
STARTUP_SOURCES=("$STARTUP_BUILD/generated/numerics.c" "$STARTUP_BUILD/generated/attention_ops.c" "$STARTUP_BUILD/generated/requant.c"
 runtime/m5/pa_m5_model.c "$STARTUP_BUILD/generated/runtime.c" "$STARTUP_BUILD/generated/cache.c" "$STARTUP_BUILD/generated/ready_cache.c"
 runtime/m5_context/score_parallel.c runtime/m5_context/smooth_cache.c runtime/m5_context/local_scores.c runtime/m5_context/parallel.c)
riscv64-unknown-elf-gcc --version | head -1 >"$STARTUP_BUILD/toolchain.txt"
for kind in "${STARTUP_KINDS[@]}"; do
  STARTUP_ENTRY="$STARTUP_BUILD/generated/attention_profile.c"
  if [[ "$kind" = runtime || "$kind" = trace ]]; then STARTUP_ENTRY="$STARTUP_BUILD/generated/runtime_entry.c"; fi
  STARTUP_EXTRA=()
  if [[ "$kind" = detail ]]; then STARTUP_EXTRA=(-DPA_CONTEXT_DIAGNOSTIC -DPA_STARTUP_DIAGNOSTIC runtime/m5_context/attention_detail.c runtime/m5_startup/detail.c); fi
  if [[ "$STARTUP_SPLIT" = 1 ]]; then
    if [[ "$kind" = trace ]]; then STARTUP_EXTRA+=(-DPA_STARTUP_TRACE_ONLY);
    else STARTUP_EXTRA+=(-DPA_STARTUP_READY_ONLY); fi
  fi
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math -fstack-usage \
    -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin -nostdlib \
    -Wl,--fatal-warnings "${STARTUP_GC[@]}" -T "$STARTUP_LINKER" "${STARTUP_INCLUDES[@]}" "${STARTUP_FLAGS[@]}" \
    "${STARTUP_EXTRA[@]}" "$STARTUP_BOOT" "$STARTUP_ENTRY" "${STARTUP_SOURCES[@]}" \
    "$STARTUP_BUILD/generated/hardware.c" -lgcc -o "$STARTUP_BUILD/m5_$kind.elf" >"$STARTUP_BUILD/$kind.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 "$STARTUP_BUILD/m5_$kind.elf" "$STARTUP_BUILD/m5_$kind.bin"
  test "$(stat -c %s "$STARTUP_BUILD/m5_$kind.bin")" = 65536
  test -z "$(riscv64-unknown-elf-nm -u "$STARTUP_BUILD/m5_$kind.elf")"
  riscv64-unknown-elf-size "$STARTUP_BUILD/m5_$kind.elf" | tee "$STARTUP_BUILD/$kind.size.txt"
  riscv64-unknown-elf-readelf -A "$STARTUP_BUILD/m5_$kind.elf" >"$STARTUP_BUILD/$kind.attributes.txt"
done
gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math -DPA_CONTEXT_TEST_THREADS -pthread \
  "${STARTUP_INCLUDES[@]}" "${STARTUP_FLAGS[@]}" "${STARTUP_SOURCES[@]}" tests/m5/model_ops_host.c \
  tests/m5_scalar/quantize_host.c zynq/m4_cpu_sfpu.c tests/m5_context/host.c tests/m5_startup/ops_host.c -lm -o "$STARTUP_BUILD/native.so"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_scalar.test_attention \
  --candidate "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/attention_test.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH="$ROOT" timeout 120 build/m4_venv/bin/python \
  tests/m5/test_numerics.py --library "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/native_test.log"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 build/m4_venv/bin/python -m "$STARTUP_READY_TEST" \
  --candidate "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/ready_test.log"
OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_context.test_combined \
  --candidate "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/combined_test.log"
OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_ops \
  --library "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/ops_test.log"
if [[ "$STARTUP_VARIANT" = cold_lut || "$STARTUP_VARIANT" = local_affine ]]; then
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_lut \
    --candidate "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/lut_test.log"
fi
if [[ "$STARTUP_VARIANT" = bounded_cache || "$STARTUP_VARIANT" = fused_project || "$STARTUP_VARIANT" = register_values || "$STARTUP_VARIANT" = interval_product || "$STARTUP_VARIANT" = packed_ops || "$STARTUP_VARIANT" = extrema_scan || "$STARTUP_VARIANT" = high_product ]]; then
  gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -Iruntime/m5_startup \
    tests/m5_startup/quant_host.c -o "$STARTUP_BUILD/quant_host.so"
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_bounded \
    --library "$STARTUP_BUILD/quant_host.so" | tee "$STARTUP_BUILD/bounded_test.log"
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_word \
    --library "$STARTUP_BUILD/quant_host.so" | tee "$STARTUP_BUILD/word_test.log"
fi
if [[ "$STARTUP_VARIANT" = fused_project || "$STARTUP_VARIANT" = register_values || "$STARTUP_VARIANT" = interval_product || "$STARTUP_VARIANT" = packed_ops || "$STARTUP_VARIANT" = extrema_scan || "$STARTUP_VARIANT" = high_product ]]; then
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_project \
    --library "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/project_test.log"
fi
if [[ "$STARTUP_VARIANT" = interval_product || "$STARTUP_VARIANT" = packed_ops || "$STARTUP_VARIANT" = extrema_scan || "$STARTUP_VARIANT" = high_product ]]; then
  STARTUP_TEST_EXTRA=()
  if [[ "$STARTUP_VARIANT" = high_product ]]; then STARTUP_TEST_EXTRA=(-DPA_STARTUP_TEST_HIGH); fi
  if [[ "$STARTUP_TEST_IMPLICIT" = 1 ]]; then STARTUP_TEST_EXTRA=(-DPA_STARTUP_TEST_IMPLICIT); fi
  gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
    "${STARTUP_INCLUDES[@]}" "${STARTUP_TEST_EXTRA[@]}" tests/m5_startup/product_host.c -o "$STARTUP_BUILD/product_host.so"
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_product \
    --library "$STARTUP_BUILD/product_host.so" | tee "$STARTUP_BUILD/product_test.log"
fi
if [[ "$STARTUP_TEST_BRANCH" = 1 ]]; then
  gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
    "${STARTUP_INCLUDES[@]}" tests/m5_startup/branch_host.c -o "$STARTUP_BUILD/branch_host.so"
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_branch \
    --library "$STARTUP_BUILD/branch_host.so" | tee "$STARTUP_BUILD/branch_test.log"
fi
if [[ "$STARTUP_TEST_BATCH" = 1 ]]; then
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_batch \
    --library "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/batch_test.log"
fi
if [[ "$STARTUP_TEST_FIXED" = 1 ]]; then
  gcc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror -fno-fast-math \
    "${STARTUP_INCLUDES[@]}" tests/m5_startup/fixed_host.c -o "$STARTUP_BUILD/fixed_host.so"
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_fixed \
    --library "$STARTUP_BUILD/fixed_host.so" | tee "$STARTUP_BUILD/fixed_test.log"
fi
if [[ "$STARTUP_REQUESTED_VARIANT" = bias_reuse || "$STARTUP_REQUESTED_VARIANT" = residual_fixed || "$STARTUP_REQUESTED_VARIANT" = rolling_fixed || "$STARTUP_REQUESTED_VARIANT" = local_rows || "$STARTUP_REQUESTED_VARIANT" = local_bias ]]; then
  OPENBLAS_NUM_THREADS=1 build/m4_venv/bin/python -m tests.m5_startup.test_bias_reuse \
    --library "$STARTUP_BUILD/native.so" | tee "$STARTUP_BUILD/bias_reuse_test.log"
fi
echo 'M5 STARTUP BUILD PASS'
