#!/usr/bin/env bash
# Isolated, finite macro-integration experiment. No full-system PPA claim.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_run_sram_probe.sh new_build_m6_directory}
case "$output" in build/m6_*) ;; *) echo 'M6 build directory required' >&2; exit 2;; esac
if [[ "$output" == *..* || -e "$output" ]]; then
  echo 'Use a new M6 directory' >&2; exit 2
fi
free_kb=$(df -Pk . | awk 'NR==2 {print $4}')
if (( free_kb < 10*1024*1024 )); then
  echo 'Less than 10 GiB free; stop before physical implementation' >&2; exit 2
fi
mkdir -p "$output"
cp asic/m6/sram_probe.json "$output/config.json"
cp asic/m6/sram_probe_pdn.tcl "$output/"
cp asic/m6/rtl/pa_m6_sram_probe.v "$output/"
cp build/m6_sram512_v1/* "$output/"
if [[ ${M6_SRAM_ADD_BOUNDARY:-0} == 1 ]]; then
  build/m6_tools_venv/bin/python scripts/m6_add_pr_boundary.py \
    build/m6_sram512_v1/sram22_512x32m4w8.gds.gz \
    build/m6_sram512_v1/sram22_512x32m4w8.lef \
    "$output/sram22_512x32m4w8_boundary.gds.gz" > "$output/boundary_check.json"
  # The original macro GDS remains alongside the new metadata-only view.
  jq '.MACROS.sram22_512x32m4w8.gds = ["dir::sram22_512x32m4w8_boundary.gds.gz"]' \
    asic/m6/sram_probe.json > "$output/config.json"
fi
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")"
# The named container allows safe targeted cleanup if the finite timeout fires.
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=20s 900s docker run --rm --name "$container" \
  --network none --cpus 8 --memory 12g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/$output,dst=/work" \
  --mount "type=bind,src=$PWD/build/m6_pdks,dst=/pdk,readonly" \
  --workdir /work --entrypoint openlane "$image" \
  --pdk-root /pdk --pdk sky130A --scl sky130_fd_sc_hd \
  --run-tag probe_v1 /work/config.json
