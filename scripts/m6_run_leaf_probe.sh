#!/usr/bin/env bash
# Local-clock-leaf probe only; original bank/full-core runners are unchanged.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_run_leaf_probe.sh build/m6_bank_probe new_tag [openlane args]}
tag=${2:?fresh tag required}
shift 2
[[ "$output" == build/m6_* && "$output" != *..* && -f "$output/manifest.json" ]] || exit 2
[[ "$tag" =~ ^[a-zA-Z0-9_]+$ && ! -e "$output/runs/$tag" && ! -e "$output/${tag}_console.log" ]] || exit 2
[[ $(jq -r .macro_count "$output/manifest.json") == 8 ]] || exit 2
[[ $(jq -r .DESIGN_NAME "$output/config.json") == pa_m6_bank_probe ]] || exit 2
free_kb=$(df -Pk "$output" | awk 'NR==2 {print $4}')
(( free_kb >= 4*1024*1024 )) || exit 2
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")-$tag"
sha256sum asic/m6/leaf_probe_entry.py asic/m6/leaf_probe_cts.tcl scripts/m6_run_leaf_probe.sh \
  > "$output/${tag}_flow_sources.sha256"
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=20s 900s docker run --rm --name "$container" \
  --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/$output,dst=/work" \
  --mount "type=bind,src=$PWD/build/m6_pdks,dst=/pdk,readonly" \
  --mount "type=bind,src=$PWD/asic/m6,dst=/m6_flow,readonly" \
  --workdir /work --entrypoint python3 "$image" /m6_flow/leaf_probe_entry.py --flow M6LeafProbe \
  --pdk-root /pdk --pdk sky130A --scl sky130_fd_sc_hd \
  --run-tag "$tag" "$@" /work/config.json > "$output/${tag}_console.log" 2>&1
