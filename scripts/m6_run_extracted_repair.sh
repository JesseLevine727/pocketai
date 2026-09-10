#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_run_extracted_repair.sh build/m6_contract_probe fresh_tag state [options]}
tag=${2:?fresh tag required}
initial=${3:?retained candidate state required}
shift 3
[[ "$output" == build/m6_* && "$output" != *..* && -f "$output/manifest.json" ]] || exit 2
[[ "$tag" =~ ^[a-zA-Z0-9_]+$ && ! -e "$output/runs/$tag" && ! -e "$output/${tag}_console.log" ]] || exit 2
[[ "$initial" == /candidate/runs/*/state_out.json && "$initial" != *..* ]] || exit 2
[[ -f "$output/${initial#/candidate/}" ]] || exit 2
free_kb=$(df -Pk "$output" | awk 'NR==2 {print $4}')
(( free_kb >= 4*1024*1024 )) || exit 2
mkdir "$output/${tag}_flow"
cp asic/m6/extracted_repair_entry.py asic/m6/extracted_repair.tcl asic/m6/bank_probe_95.sdc "$output/${tag}_flow/"
sha256sum asic/m6/extracted_repair_entry.py asic/m6/extracted_repair.tcl asic/m6/bank_probe_95.sdc \
   scripts/m6_run_extracted_repair.sh > "$output/${tag}_flow_sources.sha256"
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")-$tag"
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=20s 600s docker run --rm --name "$container" \
  --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/build/m6_bank_1x_probe_v2,dst=/work,readonly" \
  --mount "type=bind,src=$PWD/$output,dst=/candidate" \
  --mount "type=bind,src=$PWD/build/m6_pdks,dst=/pdk,readonly" \
  --mount "type=bind,src=$PWD/$output/${tag}_flow,dst=/m6_flow,readonly" \
  --workdir /candidate --entrypoint python3 "$image" /m6_flow/extracted_repair_entry.py --flow M6ExtractedFlow \
  --pdk-root /pdk --pdk sky130A --scl sky130_fd_sc_hd --design-dir /candidate \
  --run-tag "$tag" --only M6Repair.Extracted --with-initial-state "$initial" \
  -c CLOCK_PERIOD=10.526315789474 -c PNR_SDC_FILE=/m6_flow/bank_probe_95.sdc \
  -c SIGNOFF_SDC_FILE=/m6_flow/bank_probe_95.sdc -c RUN_POST_GRT_DESIGN_REPAIR=true \
  -c 'RSZ_CORNERS=min_ff_n40C_1v95 nom_tt_025C_1v80 max_ss_100C_1v60' \
  "$@" /candidate/config.json > "$output/${tag}_console.log" 2>&1
