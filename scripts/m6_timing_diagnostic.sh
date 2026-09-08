#!/usr/bin/env bash
# Read-only targeted timing; neither the prior checkpoint nor its SDC is edited.
set -euo pipefail
cd "$(dirname "$0")/.."
stage=${1:?usage: m6_timing_diagnostic.sh build/m6_stage env.tcl input.odb input.sdc new.log}
environment=${2:?}; database=${3:?}; constraints=${4:?}; log=${5:?}
[[ "$stage" == build/m6_* && "$stage" != *..* && -d "$stage" ]] || exit 2
for path in "$environment" "$database" "$constraints" "$log"; do
  [[ "$path" != /* && "$path" != *..* ]] || exit 2
done
[[ ! -e "$stage/$log" ]] || exit 2
image=$(jq -r .container asic/m6/tools.json)
timeout --signal=TERM --kill-after=20s 180s docker run --rm --network none \
  --cpus 4 --memory 8g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/$stage,dst=/work,readonly" \
  --mount "type=bind,src=$PWD/build/m6_pdks,dst=/pdk,readonly" \
  --mount "type=bind,src=$PWD/asic/m6,dst=/m6_flow,readonly" \
  -e "M6_DIAG_ENV=/work/$environment" -e "M6_DIAG_ODB=/work/$database" \
  -e "M6_DIAG_SDC=/work/$constraints" \
  --workdir /work --entrypoint python3 "$image" -c \
  'import os, subprocess, sys; from openlane.common import get_script_dir; os.environ["SCRIPTS_DIR"]=get_script_dir(); sys.exit(subprocess.call(["openroad", "-exit", "-no_splash", "/m6_flow/timing_diagnostic.tcl"]))' \
  > "$stage/$log" 2>&1
rg 'M6 TIMING DIAGNOSTIC COMPLETE' "$stage/$log"
