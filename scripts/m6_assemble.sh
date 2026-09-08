#!/usr/bin/env bash
# Assemble mapped full-system RTL without changing the normalized input.
set -euo pipefail
cd "$(dirname "$0")/.."
mapping=${1:?usage: m6_assemble.sh build/m6_mapping new_build_m6_output}
output=${2:?new output required}
for path in "$mapping" "$output"; do
  [[ "$path" == build/m6_* && "$path" != *..* ]] || exit 2
done
[[ -f "$mapping/mapped.json" && ! -e "$output" ]] || exit 2
mkdir "$output"
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")"
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=20s 180s docker run --rm --name "$container" \
  --network none --cpus 8 --memory 12g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/$mapping,dst=/input,readonly" \
  --mount "type=bind,src=$PWD/asic/m6/rtl,dst=/rtl,readonly" \
  --mount "type=bind,src=$PWD/build/m6_sram512_v1,dst=/sram,readonly" \
  --mount "type=bind,src=$PWD/$output,dst=/work" --workdir /work --entrypoint yosys "$image" -Q -T -p \
  'read_json /input/mapped.json; read_verilog -sv /input/wrappers.sv /rtl/pa_m6_sram_1w2r.sv; read_verilog -sv -lib /sram/sram22_512x32m4w8.v; hierarchy -check -top pa_m6_portable; proc; opt; memory_map; opt; opt_expr -undriven; opt_clean; check -assert; write_verilog -noattr portable.v; write_json portable.json; stat' \
  > "$output/run.log" 2>&1
