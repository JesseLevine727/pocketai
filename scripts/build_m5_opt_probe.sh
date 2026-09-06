#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
M5_OPT_BUILD=$(realpath -m "${M5_OPT_PROBE_BUILD:-$ROOT/build/m5_opt_probe}")
if [[ -e "$M5_OPT_BUILD" ]]; then echo 'use a fresh probe build directory' >&2; exit 1; fi
mkdir -p "$M5_OPT_BUILD"
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding \
  -fno-builtin -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
  -Iruntime/m5 firmware/m5/memory_test_start.S firmware/m5_opt/probe_firmware.c \
  runtime/m5_opt/pa_m5_metadata_opt.c -lgcc -o "$M5_OPT_BUILD/probe.elf"
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_OPT_BUILD/probe.elf" "$M5_OPT_BUILD/probe.bin"
test "$(stat -c %s "$M5_OPT_BUILD/probe.bin")" = 65536
test -z "$(riscv64-unknown-elf-nm -u "$M5_OPT_BUILD/probe.elf")"
riscv64-unknown-elf-size "$M5_OPT_BUILD/probe.elf" | tee "$M5_OPT_BUILD/size.txt"
sha256sum firmware/m5_opt/probe_firmware.c firmware/m5/memory_test_start.S \
  firmware/m5/memory_test.ld runtime/m5_opt/*.c runtime/m5/pa_m5_numerics.* \
  scripts/build_m5_opt_probe.sh "$M5_OPT_BUILD/probe.bin" >"$M5_OPT_BUILD/sha256.txt"
