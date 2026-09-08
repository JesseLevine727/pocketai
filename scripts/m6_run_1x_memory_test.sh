#!/usr/bin/env bash
# Bounded unit-contract test for either isolated 1x adapter candidate.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_run_1x_memory_test.sh new_build_m6_output [binary|onehot]}
variant=${2:-binary}
[[ "$output" == build/m6_* && "$output" != *..* && ! -e "$output" ]] || exit 2
case "$variant" in
  binary) adapter=asic/m6/rtl/pa_m6_sram_1x_candidate.sv ;;
  onehot) adapter=asic/m6/rtl/pa_m6_sram_1x_onehot.sv ;;
  *) exit 2 ;;
esac
mkdir "$output"
export VERILATOR_ROOT=/home/elfo/tools/verilator/root
sha256sum "$adapter" tests/m6/sram_1x_tb.sv \
  build/m6_sram512_v1/sram22_512x32m4w8.v > "$output/inputs.sha256"
timeout --signal=TERM --kill-after=10s 180s /home/elfo/tools/verilator/usr/bin/verilator \
  --binary --timing --assert --top-module sram_1x_tb --Mdir "$output/obj" -j 4 -Wno-fatal \
  tests/m6/sram_1x_tb.sv "$adapter" build/m6_sram512_v1/sram22_512x32m4w8.v \
  > "$output/build.log" 2>&1
timeout 30s "$output/obj/Vsram_1x_tb" > "$output/run.log" 2>&1
rg 'M6 .* PASS' "$output/run.log"
