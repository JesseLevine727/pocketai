#!/usr/bin/env bash
# Build the shared two-hart M1 acceptance firmware and a 64 KiB RAM image.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

CT="sim/cluster_test"
OUT="build/pa_cluster"
mkdir -p "$OUT"

bash scripts/check_deps.sh sim

riscv32-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror \
  -nostdlib -ffreestanding \
  -T "$CT/link.ld" "$CT/crt0.S" "$CT/main.c" -o "$OUT/cluster.elf"

riscv32-unknown-elf-objcopy -O binary --gap-fill 0 \
  "$OUT/cluster.elf" "$OUT/cluster.bin"
truncate -s 65536 "$OUT/cluster.bin"

if [[ "$(stat -c %s "$OUT/cluster.bin")" -ne 65536 ]]; then
  echo "[build_m1_firmware] FAIL: RAM image is not exactly 64 KiB" >&2
  exit 1
fi

echo "[build_m1_firmware] built $OUT/cluster.elf and 64 KiB cluster.bin"
