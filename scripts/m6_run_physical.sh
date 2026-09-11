#!/usr/bin/env bash
# Bounded, resumable full-core implementation. No silent qualification waivers.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_run_physical.sh build/m6_trial run_tag [openlane arguments]}
tag=${2:?run tag required}
shift 2
[[ "$output" == build/m6_* && "$output" != *..* && -f "$output/config.json" ]] || exit 2
[[ "$tag" =~ ^[a-zA-Z0-9_]+$ ]] || exit 2
if [[ -e "$output/runs/$tag" ]]; then
  echo 'Retain completed/failed run directories; use a fresh tag and --with-initial-state' >&2; exit 2
fi
free_kb=$(df -Pk . | awk 'NR==2 {print $4}')
if (( free_kb < 10*1024*1024 )); then
  echo 'Less than 10 GiB free; stop before physical implementation' >&2; exit 2
fi
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")-$tag"
sha256sum asic/m6/openlane_entry.py asic/m6/cts.tcl asic/m6/clock_data_boundaries.tcl \
  > "$output/${tag}_flow_sources.sha256"
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=20s "${M6_TIMEOUT:-1800s}" docker run --rm --name "$container" \
  --network none --cpus 8 --memory 12g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/$output,dst=/work" \
  --mount "type=bind,src=$PWD/build/m6_pdks,dst=/pdk,readonly" \
  --mount "type=bind,src=$PWD/asic/m6,dst=/m6_flow,readonly" \
  --workdir /work --entrypoint python3 "$image" /m6_flow/openlane_entry.py --flow "${M6_FLOW:-M6Classic}" \
  --pdk-root /pdk --pdk sky130A --scl sky130_fd_sc_hd \
  --run-tag "$tag" "$@" /work/config.json
