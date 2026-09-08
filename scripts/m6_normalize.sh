#!/usr/bin/env bash
# Reproduce the accepted full-system front end in a fresh M6-only directory.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_normalize.sh new_build_m6_output}
[[ "$output" == build/m6_* && "$output" != *..* && ! -e "$output" ]] || exit 2
python3 -m scripts.m6_stage_rtl "$output" \
  --generic-clock-gate --portable-syntax --asic-register-file
image=$(jq -r .container asic/m6/tools.json)
container="pocketai-$(basename "$output")"
trap 'docker stop --time 10 "$container" >/dev/null 2>&1 || true' EXIT
(
  cd "$output"
  mapfile -t m6_sv_args < sv2v.args
  timeout --signal=TERM --kill-after=10s 180s \
    ../m6_sv2v_tools/sv2v-Linux/sv2v "${m6_sv_args[@]}" \
    > converted.v 2> conversion.stderr
)
timeout --signal=TERM --kill-after=20s 180s docker run --rm --name "$container" \
  --network none --cpus 8 --memory 12g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/$output,dst=/work" --workdir /work \
  --entrypoint yosys "$image" -Q -T -p \
  'read_verilog -sv converted.v; hierarchy -check -top pa_cluster_m5_board; proc; opt; memory_dff; memory_share; opt_clean; memory_collect; write_json normalized.json; stat' \
  > "$output/elaboration.log" 2>&1
