#!/usr/bin/env bash
# Small 8-macro experiment only. Full-core 10-GiB storage guard is unchanged.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_run_bank_probe.sh build/m6_bank_trial new_tag [openlane arguments]}
tag=${2:?fresh run tag required}
shift 2
[[ "$output" == build/m6_* && "$output" != *..* && -f "$output/manifest.json" ]] || exit 2
[[ "$tag" =~ ^[a-zA-Z0-9_]+$ && ! -e "$output/runs/$tag" && ! -e "$output/${tag}_console.log" ]] || exit 2
[[ $(jq -r .macro_count "$output/manifest.json") == 8 ]] || exit 2
[[ $(jq -r .DESIGN_NAME "$output/config.json") == pa_m6_bank_probe ]] || exit 2
# Prior single-SRAM flow retained ~304 MiB. Reserve at least 4 GiB for this
# bounded small cluster; this does not authorize a low-space full-core run.
free_kb=$(df -Pk "$output" | awk 'NR==2 {print $4}')
if (( free_kb < 4*1024*1024 )); then
  echo 'Less than 4 GiB free; stop small memory experiment' >&2; exit 2
fi
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")-$tag"
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=20s 900s docker run --rm --name "$container" \
  --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/$output,dst=/work" \
  --mount "type=bind,src=$PWD/build/m6_pdks,dst=/pdk,readonly" \
  --workdir /work --entrypoint openlane "$image" \
  --pdk-root /pdk --pdk sky130A --scl sky130_fd_sc_hd \
  --run-tag "$tag" "$@" /work/config.json > "$output/${tag}_console.log" 2>&1
