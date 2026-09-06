#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
M5_OPT_BUILD=$(realpath -m "${M5_OPT_PROFILE_BUILD:-$ROOT/build/m5_opt_profile}")
if [[ -e "$M5_OPT_BUILD" ]]; then echo 'use a fresh profile build directory' >&2; exit 1; fi
mkdir -p "$M5_OPT_BUILD"
M5_OPT_NUMERICS=runtime/m5/pa_m5_numerics.c
M5_OPT_OPS=runtime/m5/pa_m5_ops.c
case "${M5_OPT_VARIANT:-baseline}" in
  baseline) ;;
  exact) M5_OPT_NUMERICS=runtime/m5_opt/pa_m5_numerics_opt.c ;;
  metadata) M5_OPT_NUMERICS=runtime/m5_opt/pa_m5_metadata_opt.c ;;
  reuse) M5_OPT_NUMERICS=runtime/m5_opt/pa_m5_metadata_opt.c
         M5_OPT_OPS=runtime/m5_opt/pa_m5_ops_opt.c ;;
  *) echo 'unknown M5_OPT_VARIANT' >&2; exit 1 ;;
esac
riscv64-unknown-elf-gcc --version | head -1 >"$M5_OPT_BUILD/toolchain.txt"
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding \
  -fno-builtin -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
  -Iruntime/m5 firmware/m5/memory_test_start.S firmware/m5_opt/profile_firmware.c \
  "$M5_OPT_NUMERICS" runtime/m5/pa_m5_model.c "$M5_OPT_OPS" \
  runtime/m5/pa_m5_runtime.c runtime/m5/pa_m5_hw.c -lgcc \
  -o "$M5_OPT_BUILD/m5_profile.elf" >"$M5_OPT_BUILD/build.log" 2>&1
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_OPT_BUILD/m5_profile.elf" "$M5_OPT_BUILD/m5_profile.bin"
test "$(stat -c %s "$M5_OPT_BUILD/m5_profile.bin")" = 65536
riscv64-unknown-elf-readelf -A "$M5_OPT_BUILD/m5_profile.elf" >"$M5_OPT_BUILD/attributes.txt"
test -z "$(riscv64-unknown-elf-nm -u "$M5_OPT_BUILD/m5_profile.elf")"
riscv64-unknown-elf-size "$M5_OPT_BUILD/m5_profile.elf" | tee "$M5_OPT_BUILD/size.txt"
sha256sum firmware/m5_opt/profile_firmware.c "$M5_OPT_NUMERICS" runtime/m5_opt/*.c runtime/m5/*.c runtime/m5/*.h \
  scripts/build_m5_opt_profile.sh "$M5_OPT_BUILD/m5_profile.bin" \
  >"$M5_OPT_BUILD/sha256.txt"
echo "M5 OPT PROFILE BUILD PASS $M5_OPT_BUILD"
