#!/usr/bin/env bash
# Fresh, bounded 95-MHz local-memory builds with retained source snapshots.
# Optional overrides are explicit OpenLane options, not silent gate relaxations.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_run_memory_closure.sh build/m6_contract_probe fresh_tag [openlane options]}
tag=${2:?fresh tag required}
shift 2
[[ "$output" == build/m6_* && "$output" != *..* && -f "$output/manifest.json" ]] || exit 2
[[ "$tag" =~ ^[a-zA-Z0-9_]+$ && ! -e "$output/runs/$tag" && ! -e "$output/${tag}_console.log" ]] || exit 2
[[ $(jq -r .macro_count "$output/manifest.json") == 8 ]] || exit 2
free_kb=$(df -Pk "$output" | awk 'NR==2 {print $4}')
(( free_kb >= 4*1024*1024 )) || exit 2
mkdir "$output/${tag}_flow"
cp asic/m6/local95_probe_entry.py asic/m6/local95_probe_cts.tcl asic/m6/bank_probe_95.sdc \
   asic/m6/contract_probe_entry.py asic/m6/contract_probe_cts.tcl asic/m6/leaf_probe_cts.tcl "$output/${tag}_flow/"
sha256sum asic/m6/local95_probe_entry.py asic/m6/local95_probe_cts.tcl asic/m6/bank_probe_95.sdc \
   asic/m6/contract_probe_entry.py asic/m6/contract_probe_cts.tcl asic/m6/leaf_probe_cts.tcl \
   scripts/m6_run_memory_closure.sh > "$output/${tag}_flow_sources.sha256"
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")-$tag"
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=20s 900s docker run --rm --name "$container" \
  --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/build/m6_bank_1x_probe_v2,dst=/work,readonly" \
  --mount "type=bind,src=$PWD/$output,dst=/candidate" \
  --mount "type=bind,src=$PWD/build/m6_pdks,dst=/pdk,readonly" \
  --mount "type=bind,src=$PWD/$output/${tag}_flow,dst=/m6_flow,readonly" \
  --workdir /candidate --entrypoint python3 "$image" /m6_flow/local95_probe_entry.py --flow M6Local95Probe \
  --pdk-root /pdk --pdk sky130A --scl sky130_fd_sc_hd --design-dir /candidate \
  --run-tag "$tag" \
  -c CLOCK_PERIOD=10.526315789474 -c PNR_SDC_FILE=/m6_flow/bank_probe_95.sdc \
  -c SIGNOFF_SDC_FILE=/m6_flow/bank_probe_95.sdc \
  -c M6_CONTRACT_CLOCK_LEAVES=true -c CTS_SINK_CLUSTERING_SIZE=1 \
  -c CTS_SINK_CLUSTERING_MAX_DIAMETER=20 -c CTS_CORNERS=max_ss_100C_1v60 \
  -c 'CTS_CLK_BUFFERS=sky130_fd_sc_hd__clkbuf_16 sky130_fd_sc_hd__clkbuf_8 sky130_fd_sc_hd__clkbuf_4' \
  -c RUN_POST_GRT_DESIGN_REPAIR=true \
  -c 'RSZ_CORNERS=min_ff_n40C_1v95 nom_tt_025C_1v80 max_ss_100C_1v60' \
  -c RUN_POST_GRT_RESIZER_TIMING=true -c GRT_RESIZER_HOLD_SLACK_MARGIN=0.15 \
  -c GRT_RESIZER_SETUP_SLACK_MARGIN=0.25 "$@" /candidate/config.json > "$output/${tag}_console.log" 2>&1
