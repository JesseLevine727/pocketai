#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source_dir=${1:?usage: m6_run_chip_test.sh build/m6_digital_core new_build_m6_test}
output=${2:?output required}
[[ "$source_dir" == build/m6_* && "$source_dir" != *..* && -f "$source_dir/manifest.json" ]] || exit 2
[[ "$output" == build/m6_* && "$output" != *..* && ! -e "$output" ]] || exit 2
mkdir "$output"
/home/elfo/tools/riscv/bin/riscv32-unknown-elf-gcc -march=rv32im_zicsr -mabi=ilp32 \
  -nostdlib -Wl,-T,tests/m6/chip_smoke.ld -Wl,--build-id=none tests/m6/chip_smoke.S -o "$output/smoke.elf"
/home/elfo/tools/riscv/bin/riscv32-unknown-elf-objcopy -O binary "$output/smoke.elf" "$output/smoke.bin"
export VERILATOR_ROOT=/home/elfo/tools/verilator/root
timeout --signal=TERM --kill-after=10s 300s /home/elfo/tools/verilator/usr/bin/verilator \
  --cc --exe --build --x-initial-edge --top-module pa_m6_chip_core --Mdir "$output/obj" -j 4 -Wno-fatal \
  "$source_dir/portable.v" "$source_dir/pa_m6_soc.sv" "$source_dir/pa_m6_clocking.sv" \
  "$source_dir/pa_m6_chip_core.sv" "$source_dir/pa_m6_spi.sv" \
  "$source_dir/pa_m6_host.sv" "$source_dir/pa_m6_uart_tx.sv" \
  build/m6_sram512_v1/sram22_512x32m4w8.v "$PWD/tests/m6/chip_smoke.cc" \
  > "$output/build.log" 2>&1
timeout --signal=TERM --kill-after=10s 120s "$output/obj/Vpa_m6_chip_core" "$output/smoke.bin" \
  > "$output/run.log" 2>&1
rg 'M6 CHIP LOADER PASS' "$output/run.log"
