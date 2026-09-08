#!/usr/bin/env bash
# Same frozen full firmware/oracle, adding assertions to an isolated candidate.
set -euo pipefail
cd "$(dirname "$0")/.."
assembly=${1:?usage: m6_run_1x_consumer_test.sh build/m6_instrumented new_build_m6_output}
output=${2:?fresh output required}
for path in "$assembly" "$output"; do
  [[ "$path" == build/m6_* && "$path" != *..* ]] || exit 2
done
[[ -f "$assembly/consumer_manifest.json" && ! -e "$output" ]] || exit 2
python3 -m scripts.m6_prepare_system_test "$output"
export VERILATOR_ROOT=/home/elfo/tools/verilator/root
timeout --signal=TERM --kill-after=10s 300s /home/elfo/tools/verilator/usr/bin/verilator \
  --cc --exe --build --assert --top-module pa_m6_cluster_core \
  --Mdir "$output/obj" -j 4 -Wno-fatal \
  "$assembly/portable.v" build/m6_sram512_v1/sram22_512x32m4w8.v \
  "$PWD/$output/test.cc" > "$output/build.log" 2>&1
timeout --signal=TERM --kill-after=10s 600s \
  "$output/obj/Vpa_m6_cluster_core" "$output/test.bin" > "$output/run.log" 2>&1
rg 'ACTUAL DUAL-IBEX ACCELERATOR PASS' "$output/run.log"
