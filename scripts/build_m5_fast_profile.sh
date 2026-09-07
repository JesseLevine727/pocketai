#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
M5_FAST_PROFILE_BUILD=$(realpath -m "${M5_FAST_PROFILE_BUILD:-$ROOT/build/m5_fast_fine_v1}")
if [[ -e "$M5_FAST_PROFILE_BUILD" ]]; then echo 'use a fresh build directory' >&2; exit 1; fi
mkdir -p "$M5_FAST_PROFILE_BUILD"
M5_FAST_SOURCE_FLAGS=(--fine)
if [[ "${M5_FAST_PREPARE:-0}" = 1 ]]; then M5_FAST_SOURCE_FLAGS+=(--prepare); fi
M5_FAST_EXTRA_SOURCES=()
if [[ "${M5_FAST_REQUANT:-0}" = 1 ]]; then
  M5_FAST_SOURCE_FLAGS+=(--requant)
  M5_FAST_EXTRA_SOURCES+=(runtime/m5_fast/pa_m5_requant.c)
fi
python3 -m scripts.m5_fast_firmware_sources "$M5_FAST_PROFILE_BUILD/generated" "${M5_FAST_SOURCE_FLAGS[@]}"
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding \
  -fno-builtin -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
  -Iruntime/m5 -Iruntime/m5_fast firmware/m5/memory_test_start.S \
  "$M5_FAST_PROFILE_BUILD/generated/profile.c" "$M5_FAST_PROFILE_BUILD/generated/numerics.c" \
  "$M5_FAST_PROFILE_BUILD/generated/ops.c" runtime/m5_fast/pa_m5_fine_profile.c \
  "${M5_FAST_EXTRA_SOURCES[@]}" \
  runtime/m5/pa_m5_model.c runtime/m5/pa_m5_runtime.c runtime/m5/pa_m5_hw.c -lgcc \
  -o "$M5_FAST_PROFILE_BUILD/m5_profile.elf" >"$M5_FAST_PROFILE_BUILD/build.log" 2>&1
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_FAST_PROFILE_BUILD/m5_profile.elf" "$M5_FAST_PROFILE_BUILD/m5_profile.bin"
riscv64-unknown-elf-size "$M5_FAST_PROFILE_BUILD/m5_profile.elf" | tee "$M5_FAST_PROFILE_BUILD/size.txt"
sha256sum "$M5_FAST_PROFILE_BUILD/generated/"* "$M5_FAST_PROFILE_BUILD/m5_profile.bin" \
  runtime/m5_fast/pa_m5_fine_profile.* scripts/m5_fast_firmware_sources.py \
  >"$M5_FAST_PROFILE_BUILD/artifacts.sha256"
echo "M5 FAST FINE PROFILE BUILD PASS $M5_FAST_PROFILE_BUILD"
