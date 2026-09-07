#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
M5_FAST_PROBE_BUILD=$(realpath -m "${M5_FAST_PROBE_BUILD:-$ROOT/build/m5_fast_requant_v1}")
if [[ -e "$M5_FAST_PROBE_BUILD" ]]; then echo 'use a fresh probe build' >&2; exit 1; fi
mkdir -p "$M5_FAST_PROBE_BUILD"
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding -fno-builtin \
  -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld -Iruntime/m5 -Iruntime/m5_fast \
  firmware/m5/memory_test_start.S firmware/m5_fast/requant_probe.c \
  runtime/m5_opt/pa_m5_metadata_opt.c runtime/m5_opt/pa_m5_ops_opt.c \
  runtime/m5/pa_m5_model.c runtime/m5/pa_m5_hw.c runtime/m5_fast/pa_m5_requant.c \
  -lgcc -o "$M5_FAST_PROBE_BUILD/probe.elf" >"$M5_FAST_PROBE_BUILD/build.log" 2>&1
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_FAST_PROBE_BUILD/probe.elf" "$M5_FAST_PROBE_BUILD/probe.bin"
riscv64-unknown-elf-size "$M5_FAST_PROBE_BUILD/probe.elf"
sha256sum firmware/m5_fast/requant_probe.c runtime/m5_fast/pa_m5_requant.c \
  "$M5_FAST_PROBE_BUILD/probe.bin" >"$M5_FAST_PROBE_BUILD/artifacts.sha256"
