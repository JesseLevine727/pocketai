#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
STARTUP_SIM=$(realpath -m "${M5_STARTUP_SIM_BUILD:?fresh startup directory}")
if [[ -e "$STARTUP_SIM" || "$(basename "$STARTUP_SIM")" != m5_startup_* ]]; then
  echo 'fresh startup directory required' >&2; exit 1
fi
mkdir -p "$STARTUP_SIM"
fusesoc --cores-root=sim/pa_m5_cluster --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim --work-root="$STARTUP_SIM/sim" --setup pocketai:pa:pa_m5_accelerators \
  >"$STARTUP_SIM/setup.log" 2>&1
touch "$STARTUP_SIM/sim/M5_FAST_TARGET" "$STARTUP_SIM/sim/M5_FAST_PIPELINED" \
  "$STARTUP_SIM/sim/M5_STARTUP_FETCH"
(cd "$STARTUP_SIM/sim" && bash ./m5_prepare_lsu.sh) >"$STARTUP_SIM/lsu.log" 2>&1
python3 -m scripts.m5_fast_sources "$STARTUP_SIM/sim" --prepare >"$STARTUP_SIM/parent.log"
STARTUP_RETURN_FLAGS=()
if [[ "${M5_STARTUP_DIRECT_RETURN:-0}" = 1 ]]; then STARTUP_RETURN_FLAGS=(--direct-return); fi
if [[ "${M5_STARTUP_REGISTERED_FALLBACK:-0}" = 1 ]]; then STARTUP_RETURN_FLAGS+=(--registered-fallback); fi
if [[ "${M5_STARTUP_EARLY_LOCAL:-0}" = 1 ]]; then STARTUP_RETURN_FLAGS+=(--early-local); fi
if [[ "${M5_STARTUP_PREFETCH:-0}" = 1 ]]; then STARTUP_RETURN_FLAGS+=(--prefetch); fi
if [[ "${M5_STARTUP_SYNC_LOOKAHEAD:-0}" = 1 ]]; then STARTUP_RETURN_FLAGS+=(--sync-lookahead); fi
if [[ "${M5_STARTUP_DATA_READ_MIRROR:-0}" = 1 ]]; then STARTUP_RETURN_FLAGS+=(--data-read-mirror); fi
if [[ "${M5_STARTUP_DIRECT_DATA:-0}" = 1 ]]; then STARTUP_RETURN_FLAGS+=(--direct-data); fi
python3 -m scripts.m5_startup_fetch "$STARTUP_SIM/sim" --prepare "${STARTUP_RETURN_FLAGS[@]}"
make -C "$STARTUP_SIM/sim" -j8 >"$STARTUP_SIM/build.log" 2>&1
python3 -m scripts.m5_startup_fetch "$STARTUP_SIM/sim" >"$STARTUP_SIM/qualification.log"
echo "STARTUP AUTONOMOUS FETCH MODEL PASS $STARTUP_SIM"
