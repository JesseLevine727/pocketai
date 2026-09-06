#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
BUILD_DIR=$(realpath -m "${M5_FIRMWARE_BUILD_DIR:-$ROOT/build/m5_firmware}")
if [[ -e "$BUILD_DIR" ]]; then
  echo "[build_m5_firmware] FAIL: use a fresh output directory: $BUILD_DIR" >&2
  exit 1
fi
mkdir -p "$BUILD_DIR"
CC=${M5_RISCV_CC:-riscv64-unknown-elf-gcc}
OBJCOPY=${M5_RISCV_OBJCOPY:-riscv64-unknown-elf-objcopy}
READELF=${M5_RISCV_READELF:-riscv64-unknown-elf-readelf}
NM=${M5_RISCV_NM:-riscv64-unknown-elf-nm}
SIZE=${M5_RISCV_SIZE:-riscv64-unknown-elf-size}
"$CC" --version | head -1 >"$BUILD_DIR/toolchain.txt"
"$CC" -march=rv32imc_zicsr -mabi=ilp32 -Os -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -ffreestanding \
  -fno-builtin -nostdlib -Wl,--fatal-warnings -T firmware/m5/memory_test.ld \
  -Iruntime/m5 firmware/m5/memory_test_start.S firmware/m5/runtime_firmware.c \
  runtime/m5/pa_m5_numerics.c runtime/m5/pa_m5_model.c runtime/m5/pa_m5_ops.c \
  runtime/m5/pa_m5_runtime.c runtime/m5/pa_m5_hw.c -lgcc \
  -o "$BUILD_DIR/m5_runtime.elf" >"$BUILD_DIR/build.log" 2>&1
"$OBJCOPY" -O binary --gap-fill 0 --pad-to 65536 \
  "$BUILD_DIR/m5_runtime.elf" "$BUILD_DIR/m5_runtime.bin"
test "$(stat -c %s "$BUILD_DIR/m5_runtime.bin")" = 65536
"$READELF" -A "$BUILD_DIR/m5_runtime.elf" >"$BUILD_DIR/attributes.txt"
grep -q 'rv32i2p1_m2p0_c2p0_zicsr2p0' "$BUILD_DIR/attributes.txt"
if "$READELF" -A "$BUILD_DIR/m5_runtime.elf" | grep -Eq 'rv32[^\"]*[fd][0-9]'; then
  echo "[build_m5_firmware] FAIL: firmware unexpectedly requires F/D ISA" >&2
  exit 1
fi
if [[ -n "$("$NM" -u "$BUILD_DIR/m5_runtime.elf")" ]]; then
  echo "[build_m5_firmware] FAIL: firmware has undefined symbols" >&2
  "$NM" -u "$BUILD_DIR/m5_runtime.elf" >&2
  exit 1
fi
"$SIZE" "$BUILD_DIR/m5_runtime.elf" | tee "$BUILD_DIR/size.txt"
sha256sum "$BUILD_DIR/m5_runtime.elf" "$BUILD_DIR/m5_runtime.bin" \
  >"$BUILD_DIR/sha256.txt"
echo "M5 FIRMWARE BUILD PASS $BUILD_DIR"
